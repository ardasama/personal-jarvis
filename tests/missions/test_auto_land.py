"""Automatic landing of an APPROVED mission (Wave F's last link).

Offline: the artifact tree is a temp directory and the git runner is faked, so
nothing here writes a repository. The guards themselves live in
``missions/land.py`` and are tested there; these tests cover the WIRING — which
patch is read, what land is called with, and that a failure never escapes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.missions import auto_land
from jarvis.missions.diff_summary import mission_patch_text


def _patch(name: str) -> str:
    return (
        f"diff --git a/{name} b/{name}\n"
        f"--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n-old\n+new\n"
    )


@pytest.fixture
def outputs(tmp_path: Path) -> Path:
    return tmp_path / "outputs"


def _write_task_patch(outputs: Path, mission_id: str, task: str, text: str) -> None:
    artifacts = outputs / f"mission_{mission_id[:13]}" / "tasks" / task / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "diff.patch").write_text(text, encoding="utf-8")


# --------------------------------------------------------------- the patch


def test_every_task_patch_is_concatenated(outputs: Path) -> None:
    mission_id = "abcdef12-3456-7890-abcd-ef1234567890"
    _write_task_patch(outputs, mission_id, "0001", _patch("notes/one.md"))
    _write_task_patch(outputs, mission_id, "0002", _patch("notes/two.md"))

    text = mission_patch_text(outputs, mission_id)

    assert "notes/one.md" in text and "notes/two.md" in text


def test_a_mission_with_no_artifacts_yields_no_text(outputs: Path) -> None:
    assert mission_patch_text(outputs, "abcdef12-3456-7890-abcd-ef1234567890") == ""


@pytest.mark.parametrize("mission_id", ["", "   ", "../../etc", "no/slashes", "x"])
def test_an_unauthorized_mission_id_is_refused(outputs: Path, mission_id: str) -> None:
    """The directory is derived from an authorized id, never from a path."""
    assert mission_patch_text(outputs, mission_id) == ""


# ------------------------------------------------------------ the wiring


@pytest.mark.asyncio
async def test_a_mission_without_a_patch_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, outputs: Path, tmp_path: Path
) -> None:
    called = False

    async def _land(**_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(auto_land, "land", _land)

    result = await auto_land.land_approved_mission(
        "abcdef12-3456-7890-abcd-ef1234567890",
        outputs_root=outputs,
        repo=tmp_path / "repo",
    )

    assert result is None
    assert called is False  # land was never invoked


@pytest.mark.asyncio
async def test_the_state_is_stated_and_the_diff_is_the_archived_one(
    monkeypatch: pytest.MonkeyPatch, outputs: Path, tmp_path: Path
) -> None:
    mission_id = "abcdef12-3456-7890-abcd-ef1234567890"
    _write_task_patch(outputs, mission_id, "0001", _patch("notes/one.md"))
    repo = tmp_path / "repo"
    captured: dict[str, object] = {}

    async def _dirty(paths: list[str], root: Path) -> list[str]:
        captured["dirty_query"] = (list(paths), root)
        return []

    async def _land(**kwargs: object) -> object:
        captured.update(kwargs)
        from jarvis.missions.land import LandResult

        return LandResult(applied=True, detail="1 file(s) landed")

    monkeypatch.setattr(auto_land, "dirty_paths", _dirty)
    monkeypatch.setattr(auto_land, "land", _land)

    result = await auto_land.land_approved_mission(
        mission_id, outputs_root=outputs, repo=repo
    )

    assert result is not None and result.applied is True
    assert captured["state"] == "APPROVED"
    assert captured["mission_id"] == mission_id
    assert captured["repo_root"] == repo
    assert captured["run_git"] is auto_land.run_git
    assert "notes/one.md" in str(captured["diff_text"])
    assert captured["dirty_query"] == (["notes/one.md"], repo)


@pytest.mark.asyncio
async def test_a_broken_landing_never_escapes(
    monkeypatch: pytest.MonkeyPatch, outputs: Path, tmp_path: Path
) -> None:
    async def _boom(**_kwargs: object) -> None:
        raise RuntimeError("git exploded")

    monkeypatch.setattr(auto_land, "dirty_paths", _no_dirty)
    monkeypatch.setattr(auto_land, "land", _boom)
    _write_task_patch(
        outputs, "abcdef12-3456-7890-abcd-ef1234567890", "0001", _patch("a.md")
    )

    result = await auto_land.land_approved_mission(
        "abcdef12-3456-7890-abcd-ef1234567890",
        outputs_root=outputs,
        repo=tmp_path / "repo",
    )

    assert result is None  # the state machine must never see the error


async def _no_dirty(paths: list[str], root: Path) -> list[str]:
    return []


@pytest.mark.asyncio
async def test_git_status_failure_treats_every_target_as_dirty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Fails CLOSED: without proof of cleanliness the landing must refuse."""

    async def _fail(argv: list[str], cwd: Path) -> tuple[int, str]:
        return 1, "fatal: not a git repository"

    monkeypatch.setattr(auto_land, "run_git", _fail)

    dirty = await auto_land.dirty_paths(["a.md", "b.md"], tmp_path)

    assert dirty == ["a.md", "b.md"]


@pytest.mark.asyncio
async def test_git_status_separates_dirty_from_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _ok(argv: list[str], cwd: Path) -> tuple[int, str]:
        return 0, " M notes/dirty.md\n"

    monkeypatch.setattr(auto_land, "run_git", _ok)

    assert await auto_land.dirty_paths(["notes/dirty.md", "notes/clean.md"], tmp_path) == [
        "notes/dirty.md"
    ]


@pytest.mark.asyncio
async def test_the_manager_wrapper_calls_the_lander(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jarvis.missions.manager import MissionManager

    seen: list[str] = []

    async def _land(mission_id: str, **_kwargs: object) -> None:
        seen.append(mission_id)

    monkeypatch.setattr(
        "jarvis.missions.auto_land.land_approved_mission", _land
    )

    manager = MissionManager.__new__(MissionManager)  # bypass the heavy __init__
    await manager._maybe_land("mission-1")

    assert seen == ["mission-1"]
