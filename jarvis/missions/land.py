"""Land an APPROVED mission's diff into the product tree — guarded, backed up.

A mission runs in its own ``git worktree`` and its workers never run git
(AP-10): the parent runtime captures the diff and lands it. That last step had
no home in the product — an APPROVED mission left its work in the worktree and
nothing brought it back.

Landing is the one operation that writes the user's OWN tree, so the guards
come first and every file it touches is copied to a uniquely named backup
BEFORE the patch is applied:

* only an ``APPROVED`` mission lands;
* the mission's own ``path_guard`` refuses a diff that touches a blocked path
  (the existing product rule, not a new one);
* a path that escapes the repo root, is binary, deletes a file, is missing on
  disk, or is already dirty in the SHARED working tree (other agent sessions
  edit the same checkout) refuses the whole landing;
* ``git apply`` runs in the SAME process and the same tree — never a merge,
  never a rebase, never ``--force``;
* if the patch does not apply, every touched file is restored from its backup
  and the failure is reported with what was restored.

Nothing is ever deleted. Backup directories are FIFO-capped (the ten most
recent landings are kept), the same policy ``core/self_mod`` already uses for
its own backups.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jarvis.missions.diff_summary import summarize_unified_diff
from jarvis.missions.safety.path_guard import filter_diff_paths

log = logging.getLogger(__name__)

LAND_BACKUP_SUBDIR = "backups/mission_land"
AUDIT_FILE_NAME = "mission_land_audit.jsonl"
_BACKUP_KEEP = 10
_TS_FORMAT = "%Y%m%dT%H%M%S_%fZ"

# Decision codes ``preflight`` returns. An empty list means "may land".
NOT_APPROVED = "not_approved"
EMPTY_DIFF = "empty_diff"
TRUNCATED_DIFF = "truncated_diff"
BINARY_FILE = "binary_file"
DELETED_TARGET = "deleted_target"
BLOCKED_PATH = "blocked_path"
OUTSIDE_ROOT = "outside_root"
MISSING_TARGET = "missing_target"
DIRTY_TARGET = "dirty_target"

#: ``(argv, cwd) -> (returncode, output)``. Injected so the tests never touch a
#: real repository and production always runs in the real tree.
GitRunner = Callable[[list[str], Path], Awaitable[tuple[int, str]]]


@dataclass(frozen=True)
class LandResult:
    """What a landing attempt did, in terms a caller can act on."""

    applied: bool
    refusals: list[dict[str, str]] = field(default_factory=list)
    backups: dict[str, str] = field(default_factory=dict)
    detail: str = ""
    audit: str = ""


def backup_root() -> Path:
    """``DATA_DIR/backups/mission_land`` — resolved at call time."""
    from jarvis.core import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / LAND_BACKUP_SUBDIR


def audit_path() -> Path:
    """``DATA_DIR/state/mission_land_audit.jsonl`` — resolved at call time."""
    from jarvis.core import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / "state" / AUDIT_FILE_NAME


def _safe_target(root: Path, rel: str) -> Path | None:
    """The absolute path of ``rel`` inside ``root``, or ``None`` if it escapes.

    A ``..`` segment, an absolute path or a symlinked directory that resolves
    outside the repo is not ours to write (the same rule the agentic-IDE and
    attachment paths already enforce).
    """
    cleaned = str(rel or "").strip().replace("\\", "/").lstrip("/")
    if not cleaned:
        return None
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    try:
        resolved = (root / Path(*parts)).resolve()
    except OSError:
        return None
    return resolved if resolved.is_relative_to(root) else None


def preflight(
    *,
    state: Any,
    diff_text: str,
    repo_root: Path,
    dirty_paths: Sequence[str] = (),
    extra_globs: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    """Every reason this diff must NOT land. Empty list = safe to land."""
    code = str(getattr(state, "value", state) or "").strip().upper()
    if code != "APPROVED":
        return [{"code": NOT_APPROVED, "detail": code or "unknown"}]
    if not str(diff_text or "").strip():
        return [{"code": EMPTY_DIFF, "detail": "the mission archived no diff"}]

    summary = summarize_unified_diff(diff_text)
    files = list(summary.get("files") or [])
    refusals: list[dict[str, str]] = []
    if not files:
        return [{"code": EMPTY_DIFF, "detail": "no file section in the diff"}]
    if summary.get("truncated_files"):
        # An unenumerable diff cannot be fully guarded, so it is not landed.
        return [{"code": TRUNCATED_DIFF, "detail": "too many files to guard"}]

    # The product's own rule for what a mission may touch.
    for path in filter_diff_paths(diff_text, extra_globs=extra_globs):
        refusals.append({"code": BLOCKED_PATH, "detail": path})

    root = Path(repo_root).resolve()
    dirty = {str(p).strip().replace("\\", "/") for p in dirty_paths if str(p).strip()}
    for entry in files:
        rel = str(entry.get("path") or "")
        previous = str(entry.get("previous_path") or "")
        if entry.get("binary"):
            refusals.append({"code": BINARY_FILE, "detail": rel})
        if str(entry.get("status") or "") == "deleted":
            refusals.append({"code": DELETED_TARGET, "detail": rel})
        for path in (rel, previous):
            if not path:
                continue
            target = _safe_target(root, path)
            if target is None:
                refusals.append({"code": OUTSIDE_ROOT, "detail": path})
                continue
            if path.strip().replace("\\", "/") in dirty:
                refusals.append({"code": DIRTY_TARGET, "detail": path})
            if str(entry.get("status") or "") != "added" and not target.is_file():
                refusals.append({"code": MISSING_TARGET, "detail": path})
    return refusals


def _new_backup_dir(root: Path) -> Path:
    """A uniquely named directory for THIS landing's copies."""
    root.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        candidate = root / datetime.now(UTC).strftime(_TS_FORMAT)
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise OSError(f"could not create a unique backup directory under {root}")


def _gc_backup_dirs(root: Path, *, keep: int = _BACKUP_KEEP) -> None:
    """FIFO-cap the backup directories, keeping the most recent ``keep``.

    Counted in LANDINGS, not files, so a 40-file landing cannot push the
    others out. Failures are logged, never raised: a housekeeping miss must not
    fail a landing that already succeeded.
    """
    try:
        dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        log.debug("mission land: backup dir listing failed", exc_info=True)
        return
    for stale in dirs[:-keep] if len(dirs) > keep else []:
        try:
            shutil.rmtree(stale)
        except OSError:
            log.warning("mission land: could not prune old backup %s", stale)


def _backup_paths(paths: Sequence[str], *, repo_root: Path, backup_dir: Path) -> dict[str, str]:
    """Copy every existing target into ``backup_dir`` under a unique name."""
    copies: dict[str, str] = {}
    root = Path(repo_root).resolve()
    for rel in dict.fromkeys(str(p) for p in paths):
        target = _safe_target(root, rel)
        if target is None or not target.is_file():
            continue
        # mkstemp guarantees the name is unique across threads AND processes.
        fd, name = tempfile.mkstemp(
            suffix=".bak", prefix=f"{target.name}.", dir=str(backup_dir)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(target.read_bytes())
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    log.debug("mission land: backup fsync failed", exc_info=True)
        except BaseException:
            try:
                os.unlink(name)
            except OSError:
                pass
            raise
        copies[rel] = name
    return copies


def _restore(backups: dict[str, str], *, repo_root: Path) -> bool:
    """Put every backed-up file back. Returns False when any restore failed."""
    ok = True
    root = Path(repo_root).resolve()
    for rel, backup in backups.items():
        target = _safe_target(root, rel)
        source = Path(backup)
        if target is None or not source.is_file():
            log.warning("mission land: cannot restore %s (backup %s)", rel, backup)
            ok = False
            continue
        try:
            shutil.copyfile(source, target)
        except OSError:
            log.warning("mission land: restore of %s failed", rel, exc_info=True)
            ok = False
    return ok


def _audit(mission_id: str, outcome: str, *, path: Path | None = None, **fields: Any) -> str:
    """Append one JSON line. Paths and counts only — never file contents."""
    target = path or audit_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "mission_id": str(mission_id),
            "outcome": str(outcome),
            **{key: value for key, value in fields.items() if value not in (None, "", [], {})},
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        log.warning("mission land: could not write the audit line", exc_info=True)
        return ""
    return str(target)


async def land(
    *,
    mission_id: str,
    state: Any,
    diff_text: str,
    repo_root: Path,
    run_git: GitRunner,
    dirty_paths: Sequence[str] = (),
    extra_globs: tuple[str, ...] = (),
    backup_dir: Path | None = None,
    audit: Path | None = None,
) -> LandResult:
    """Back up every touched file, then apply ``diff_text``. Never deletes."""
    refusals = preflight(
        state=state,
        diff_text=diff_text,
        repo_root=repo_root,
        dirty_paths=dirty_paths,
        extra_globs=extra_globs,
    )
    if refusals:
        where = _audit(mission_id, "refused", path=audit, refusals=refusals)
        return LandResult(
            applied=False,
            refusals=refusals,
            detail=f"refused: {', '.join(sorted({r['code'] for r in refusals}))}",
            audit=where,
        )

    paths = [str(entry.get("path") or "") for entry in summarize_unified_diff(diff_text)["files"]]
    root = Path(repo_root)
    destination = backup_dir or backup_root()
    backups = _backup_paths(paths, repo_root=root, backup_dir=_new_backup_dir(destination))

    patch_file: Path | None = None
    try:
        fd, name = tempfile.mkstemp(suffix=".patch", prefix="mission_land_")
        patch_file = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(diff_text)
        code, output = await run_git(["apply", "--whitespace=nowarn", str(patch_file)], root)
    finally:
        if patch_file is not None:
            try:
                patch_file.unlink()
            except OSError:
                log.debug("mission land: patch tempfile removal failed", exc_info=True)

    if code != 0:
        restored = _restore(backups, repo_root=root)
        where = _audit(
            mission_id,
            "failed",
            path=audit,
            paths=paths,
            restored=restored,
            git_output=output[:200],
        )
        return LandResult(
            applied=False,
            refusals=[{"code": "patch_failed", "detail": output[:300]}],
            backups=backups,
            detail=(
                f"git apply failed ({output[:150].strip()}); "
                f"{'every touched file was restored' if restored else 'RESTORE INCOMPLETE'} "
                f"from {len(backups)} backup(s)"
            ),
            audit=where,
        )

    _gc_backup_dirs(destination)
    where = _audit(mission_id, "applied", path=audit, paths=paths, backups=len(backups))
    return LandResult(
        applied=True,
        backups=backups,
        detail=f"{len(paths)} file(s) landed, {len(backups)} backup(s) kept",
        audit=where,
    )


__all__ = [
    "AUDIT_FILE_NAME",
    "BINARY_FILE",
    "BLOCKED_PATH",
    "DELETED_TARGET",
    "DIRTY_TARGET",
    "EMPTY_DIFF",
    "LAND_BACKUP_SUBDIR",
    "MISSING_TARGET",
    "NOT_APPROVED",
    "OUTSIDE_ROOT",
    "TRUNCATED_DIFF",
    "LandResult",
    "audit_path",
    "backup_root",
    "land",
    "preflight",
]
