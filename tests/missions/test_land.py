"""Landing an APPROVED mission's diff: guarded first, backed up always.

Nothing here touches a real repository — the git runner is injected and the
backups/audit live under a temporary DATA_DIR. The guards are the point: this
is the one operation that writes the user's own tree, which other agent
sessions share.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from jarvis.missions import land as land_mod
from jarvis.missions.land import (
    BINARY_FILE,
    BLOCKED_PATH,
    DELETED_TARGET,
    DIRTY_TARGET,
    EMPTY_DIFF,
    MISSING_TARGET,
    NOT_APPROVED,
    OUTSIDE_ROOT,
    TRUNCATED_DIFF,
    land,
    preflight,
)

_ORIGINAL = "one\ntwo\nthree\n"

_DIFF = """diff --git a/notes/a.md b/notes/a.md
index 1111111..2222222 100644
--- a/notes/a.md
+++ b/notes/a.md
@@ -1,3 +1,3 @@
 one
-two
+two (edited by the mission)
 three
"""

_APPROVED = "APPROVED"


def _diff_for(path: str, *, status: str = "modified", previous: str = "") -> str:
    header = f"diff --git a/{previous or path} b/{path}\n"
    body = ""
    if status == "added":
        body += "new file mode 100644\n"
    elif status == "deleted":
        body += "deleted file mode 100644\n"
    body += f"--- a/{previous or path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"
    return header + body


def _binary_diff(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n"
        f"Binary files a/{path} and b/{path} differ\n"
    )


def _read(path: Path) -> str:
    """Blocking file IO lives in a sync helper: these tests are async."""
    return path.read_text(encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "a.md").write_text(_ORIGINAL, encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from jarvis.core import config as core_config

    target = tmp_path / "data"
    monkeypatch.setattr(core_config, "DATA_DIR", target)
    return target


def _runner(
    code: int = 0, output: str = "", on_call: Callable[[Path], None] | None = None
) -> tuple[Any, list[tuple[list[str], Path]]]:
    calls: list[tuple[list[str], Path]] = []

    async def run(argv: list[str], cwd: Path) -> tuple[int, str]:
        calls.append((list(argv), cwd))
        if on_call is not None:
            on_call(cwd)
        return code, output

    return run, calls


# ------------------------------------------------------------------ guards


def test_only_an_approved_mission_may_land(repo: Path) -> None:
    for state in ("RUNNING", "PENDING", "FAILED", "CANCELLED", None, ""):
        refusals = preflight(state=state, diff_text=_DIFF, repo_root=repo)
        assert [r["code"] for r in refusals] == [NOT_APPROVED]

    assert preflight(state=_APPROVED, diff_text=_DIFF, repo_root=repo) == []


def test_an_empty_diff_is_refused(repo: Path) -> None:
    for text in ("", "   ", "\n"):
        refusals = preflight(state=_APPROVED, diff_text=text, repo_root=repo)
        assert [r["code"] for r in refusals] == [EMPTY_DIFF]


def test_a_diff_without_a_file_section_is_refused(repo: Path) -> None:
    refusals = preflight(
        state=_APPROVED, diff_text="just prose, no diff header", repo_root=repo
    )
    assert [r["code"] for r in refusals] == [EMPTY_DIFF]


def test_a_blocked_path_is_refused(repo: Path, tmp_path: Path) -> None:
    (repo / "notes" / "keep.secret").write_text("x", encoding="utf-8")
    refusals = preflight(
        state=_APPROVED,
        diff_text=_diff_for("notes/keep.secret"),
        repo_root=repo,
        extra_globs=("*.secret",),
    )
    assert [r["code"] for r in refusals] == [BLOCKED_PATH]
    assert refusals[0]["detail"] == "notes/keep.secret"


def test_a_path_escaping_the_root_is_refused(repo: Path) -> None:
    refusals = preflight(
        state=_APPROVED, diff_text=_diff_for("../outside.md"), repo_root=repo
    )
    assert OUTSIDE_ROOT in {r["code"] for r in refusals}


def test_a_deleted_file_is_refused(repo: Path) -> None:
    refusals = preflight(
        state=_APPROVED,
        diff_text=_diff_for("notes/a.md", status="deleted"),
        repo_root=repo,
    )
    assert DELETED_TARGET in {r["code"] for r in refusals}


def test_a_binary_patch_is_refused(repo: Path) -> None:
    refusals = preflight(
        state=_APPROVED, diff_text=_binary_diff("notes/a.md"), repo_root=repo
    )
    assert BINARY_FILE in {r["code"] for r in refusals}


def test_a_dirty_target_is_refused(repo: Path) -> None:
    """The working tree is SHARED with other agent sessions."""
    refusals = preflight(
        state=_APPROVED,
        diff_text=_DIFF,
        repo_root=repo,
        dirty_paths=["notes/a.md"],
    )
    assert DIRTY_TARGET in {r["code"] for r in refusals}


def test_a_missing_target_is_refused(repo: Path) -> None:
    (repo / "notes" / "a.md").unlink()
    refusals = preflight(state=_APPROVED, diff_text=_DIFF, repo_root=repo)
    assert MISSING_TARGET in {r["code"] for r in refusals}


def test_an_added_file_needs_no_existing_target(repo: Path) -> None:
    refusals = preflight(
        state=_APPROVED,
        diff_text=_diff_for("notes/new.md", status="added"),
        repo_root=repo,
    )
    assert refusals == []


def test_a_truncated_diff_is_refused(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unenumerable diff cannot be fully guarded, so it never lands."""
    monkeypatch.setattr(
        land_mod,
        "summarize_unified_diff",
        lambda _text: {
            "files": [{"path": "notes/a.md", "status": "modified"}],
            "truncated_files": True,
        },
    )
    refusals = preflight(state=_APPROVED, diff_text=_DIFF, repo_root=repo)
    assert [r["code"] for r in refusals] == [TRUNCATED_DIFF]


# ----------------------------------------------------------------- landing


@pytest.mark.asyncio
async def test_landing_backs_up_every_touched_file_before_applying(
    repo: Path, data_dir: Path
) -> None:
    run, calls = _runner()
    result = await land(
        mission_id="m-1", state=_APPROVED, diff_text=_DIFF, repo_root=repo, run_git=run
    )

    assert result.applied is True
    assert result.detail == "1 file(s) landed, 1 backup(s) kept"
    assert calls and calls[0][1] == repo
    # Never a merge, a rebase, a force or a 3-way apply: a plain patch.
    assert calls[0][0][0] == "apply"
    assert not any(
        flag in " ".join(calls[0][0]) for flag in ("--force", "--3way", "rebase", "merge")
    )
    backup = Path(next(iter(result.backups.values())))
    assert _read(backup) == _ORIGINAL
    assert str(backup).startswith(str(data_dir))  # a backup under the user data dir
    audit_lines = _read(data_dir / "state" / "mission_land_audit.jsonl")
    assert '"outcome": "applied"' in audit_lines


@pytest.mark.asyncio
async def test_a_failed_patch_restores_every_touched_file(
    repo: Path, data_dir: Path
) -> None:
    target = repo / "notes" / "a.md"

    def _wreck(cwd: Path) -> None:
        # Simulate a partially applied patch.
        Path(cwd, "notes", "a.md").write_text("corrupted\n", encoding="utf-8")

    run, _calls = _runner(1, "error: patch failed: notes/a.md:1", on_call=_wreck)
    result = await land(
        mission_id="m-2", state=_APPROVED, diff_text=_DIFF, repo_root=repo, run_git=run
    )

    assert result.applied is False
    assert result.refusals[0]["code"] == "patch_failed"
    assert "restored" in result.detail
    assert _read(target) == _ORIGINAL
    audit_lines = _read(data_dir / "state" / "mission_land_audit.jsonl")
    assert '"outcome": "failed"' in audit_lines


@pytest.mark.asyncio
async def test_a_refused_landing_writes_no_backup_and_says_why(
    repo: Path, data_dir: Path
) -> None:
    run, calls = _runner()
    result = await land(
        mission_id="m-3",
        state="RUNNING",
        diff_text=_DIFF,
        repo_root=repo,
        run_git=run,
    )

    assert result.applied is False
    assert result.refusals[0]["code"] == NOT_APPROVED
    assert calls == []  # git was never invoked
    assert not (data_dir / "backups" / "mission_land").exists()
    audit_lines = _read(data_dir / "state" / "mission_land_audit.jsonl")
    assert '"outcome": "refused"' in audit_lines
    assert NOT_APPROVED in audit_lines


@pytest.mark.asyncio
async def test_the_audit_records_paths_never_file_contents(
    repo: Path, data_dir: Path
) -> None:
    run, _calls = _runner()
    await land(
        mission_id="m-4", state=_APPROVED, diff_text=_DIFF, repo_root=repo, run_git=run
    )

    record = _read(data_dir / "state" / "mission_land_audit.jsonl")
    assert "notes/a.md" in record
    assert "two (edited by the mission)" not in record
    assert "one\\ntwo" not in record


def test_old_backup_directories_are_pruned_not_kept_forever(data_dir: Path) -> None:
    root = data_dir / "backups" / "mission_land"
    root.mkdir(parents=True)
    for index in range(12):
        (root / f"20260101T0000{index:02d}Z").mkdir()

    land_mod._gc_backup_dirs(root)

    remaining = sorted(p.name for p in root.iterdir() if p.is_dir())
    assert len(remaining) == land_mod._BACKUP_KEEP
    # The two oldest went; the ten most recent stay.
    assert remaining[0].startswith("20260101T000002Z")
