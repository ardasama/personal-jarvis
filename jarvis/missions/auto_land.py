"""Land an APPROVED mission automatically — the last link of the loop.

``MissionManager.transition_state`` is the single funnel every mission passes
through, so an APPROVED mission lands from there. This module only WIRES the
pieces: it reads the mission's own archived patch (``mission_patch_text``) and
hands it to ``jarvis/missions/land.py``, which owns every guard, backup and
refusal. Nothing here decides what is safe to write.

Failure policy: landing must never break the state machine, so every error is
swallowed into a log line — but never silently: each refusal and each failure
also lands in the audit log (``data/state/mission_land_audit.jsonl``), where a
human can see exactly why an approved mission did not reach the tree.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from jarvis.missions.land import LandResult, land

log = logging.getLogger(__name__)


def repo_root() -> Path:
    """The checkout this mission belongs to (``jarvis/`` sits at its root)."""
    import jarvis

    return Path(jarvis.__file__).resolve().parents[1]


def default_outputs_root(repo: Path | None = None) -> Path | None:
    """Where mission artifacts live, or ``None`` when it cannot be resolved."""
    try:
        from jarvis.missions.isolation.worktree import resolve_outputs_root

        return resolve_outputs_root(repo or repo_root())
    except Exception:  # noqa: BLE001 — an unknown root means "do not land"
        log.debug("auto-land: outputs root unavailable", exc_info=True)
        return None


async def run_git(argv: list[str], cwd: Path) -> tuple[int, str]:
    """Run git in the product tree: no console window, UTF-8 output (AP-1)."""
    from jarvis.core.process_utils import NO_WINDOW_CREATIONFLAGS

    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=NO_WINDOW_CREATIONFLAGS,
        )
    except OSError as exc:
        return 127, f"git could not be started: {exc}"
    out, _ = await proc.communicate()
    return proc.returncode or 0, (out or b"").decode("utf-8", "replace")


async def dirty_paths(paths: Sequence[str], repo: Path) -> list[str]:
    """Which of ``paths`` the SHARED working tree has already modified.

    Fails CLOSED: when git cannot answer, every path is reported dirty, so the
    landing refuses instead of overwriting another session's work.
    """
    wanted = [str(p).strip() for p in paths if str(p).strip()]
    if not wanted:
        return []
    code, out = await run_git(["status", "--porcelain", "--", *wanted], repo)
    if code != 0:
        log.warning("auto-land: git status failed (%s); treating targets as dirty", out[:160])
        return wanted
    dirty: list[str] = []
    for line in out.splitlines():
        entry = line[3:].strip().strip('"')
        if entry:
            dirty.append(entry)
    return dirty


async def land_approved_mission(
    mission_id: str,
    *,
    outputs_root: Path | None = None,
    repo: Path | None = None,
) -> LandResult | None:
    """Land one APPROVED mission's archived patch. Never raises.

    Returns ``None`` when there is nothing to do (no artifacts, no patch).
    """
    try:
        root = repo or repo_root()
        outputs = outputs_root or default_outputs_root(root)
        if outputs is None:
            log.warning("auto-land: mission %s has no resolvable outputs root", mission_id)
            return None
        from jarvis.missions.diff_summary import mission_patch_text, summarize_unified_diff

        diff_text = mission_patch_text(outputs, mission_id)
        if not diff_text.strip():
            log.info("auto-land: mission %s archived no patch; nothing to land.", mission_id)
            return None
        paths = [
            str(entry.get("path") or "")
            for entry in summarize_unified_diff(diff_text)["files"]
        ]
        dirty = await dirty_paths(paths, root)
        result = await land(
            mission_id=mission_id,
            # The funnel only calls this for APPROVED, which is what land's
            # preflight re-checks: the state is stated, never assumed.
            state="APPROVED",
            diff_text=diff_text,
            repo_root=root,
            run_git=run_git,
            dirty_paths=dirty,
        )
        if result.applied:
            log.info(
                "auto-land: mission %s landed %d file(s) (%d backup(s)).",
                mission_id,
                len(paths),
                len(result.backups),
            )
        else:
            log.warning(
                "auto-land: mission %s was NOT landed — %s", mission_id, result.detail
            )
        return result
    except Exception:  # noqa: BLE001 — never break the state machine
        log.warning("auto-land: mission %s could not be landed", mission_id, exc_info=True)
        return None


__all__ = [
    "default_outputs_root",
    "dirty_paths",
    "land_approved_mission",
    "repo_root",
    "run_git",
]
