"""The measured tool-calling verdict store (AP-21: capability by behaviour).

A declaration is a claim; the store holds what a real probe measured. Every
failure mode here is *unknown*: a missing file, unreadable JSON, a digest
mismatch — never a wrong yes, and never a crash.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.brain import tool_probe_store as store


@pytest.fixture
def store_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from jarvis.core import config as core_config

    monkeypatch.setattr(core_config, "DATA_DIR", tmp_path)
    return tmp_path / "state" / store.PROBE_FILE_NAME


def test_nothing_recorded_means_no_verdict(store_path: Path) -> None:
    assert store.verdict_for("ollama", "m") is None
    assert store.reason_for("ollama", "m") is None
    assert store.entries() == {}


def test_a_refuted_model_round_trips_with_its_evidence(store_path: Path) -> None:
    path = store.write_verdict(
        "ollama",
        "deepseek-r1:8b",
        capable=False,
        reason="confabulation",
        evidence="stated a tool result without calling",
        digest="sha256:abc",
    )
    assert path == store_path
    assert store.verdict_for("ollama", "deepseek-r1:8b") is False
    assert store.reason_for("ollama", "deepseek-r1:8b") == "confabulation"
    assert store.entries()["ollama/deepseek-r1:8b"]["evidence"].startswith("stated")
    assert json.loads(store_path.read_text(encoding="utf-8"))["version"] == 1


def test_a_confirmed_model_round_trips(store_path: Path) -> None:
    store.write_verdict("ollama", "qwen3.5:4b", capable=True, reason="tool_calls")
    assert store.verdict_for("ollama", "qwen3.5:4b") is True
    assert store.reason_for("ollama", "qwen3.5:4b") == "tool_calls"


def test_models_do_not_shadow_each_other(store_path: Path) -> None:
    store.write_verdict("ollama", "a", capable=False, reason="no_tool_call")
    store.write_verdict("ollama", "b", capable=True, reason="tool_calls")
    assert store.verdict_for("ollama", "a") is False
    assert store.verdict_for("ollama", "b") is True
    assert store.verdict_for("openai", "a") is None


def test_a_repull_invalidates_the_measurement(store_path: Path) -> None:
    """Different weights must not inherit the old verdict."""
    store.write_verdict(
        "ollama", "m", capable=False, reason="no_tool_call", digest="sha256:old"
    )
    assert store.verdict_for("ollama", "m", digest="sha256:new") is None
    assert store.verdict_for("ollama", "m", digest="sha256:old") is False
    # A caller that cannot see a digest still reads the recorded verdict.
    assert store.verdict_for("ollama", "m") is False


def test_a_corrupt_store_is_unknown_not_a_crash(store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text("{not json", encoding="utf-8")
    assert store.verdict_for("ollama", "m") is None
    assert store.entries() == {}
    # ...and a later write repairs it.
    store.write_verdict("ollama", "m", capable=True, reason="tool_calls")
    assert store.verdict_for("ollama", "m") is True


def test_a_store_with_a_wrong_shape_is_unknown(store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    assert store.entries() == {}
    assert store.verdict_for("ollama", "m") is None


def test_a_non_boolean_verdict_is_unknown(store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps({"version": 1, "entries": {"ollama/m": {"capable": "yes"}}}),
        encoding="utf-8",
    )
    assert store.verdict_for("ollama", "m") is None


def test_the_write_leaves_no_temp_files_behind(store_path: Path) -> None:
    store.write_verdict("ollama", "m", capable=True, reason="tool_calls")
    leftovers = [
        p.name for p in store_path.parent.iterdir() if p.name != store.PROBE_FILE_NAME
    ]
    assert leftovers == []


def test_blank_identifiers_are_refused(store_path: Path) -> None:
    assert store.write_verdict("", "m", capable=True, reason="tool_calls") is None
    assert store.verdict_for("ollama", "") is None
    assert store.verdict_for("", "m") is None
