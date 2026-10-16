"""The opt-in behavioural tool probe in ``scripts/check_local_models.py``.

Offline: the response classifier is a pure function and the probe loop runs
against a fake inventory with a scripted answer, so nothing loads a model and
nothing touches a network. Live 2026-10-16: ``deepseek-r1:8b`` declared
``tools``, fabricated a result and never called one; ``qwen3.5:4b`` called it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_local_models.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_local_models_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------- the classifier


def test_a_real_tool_call_is_capable() -> None:
    module = _load()
    capable, reason, evidence = module.classify_probe_response(
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "get_weather", "arguments": {}}}],
            }
        }
    )
    assert capable is True
    assert reason == "tool_calls"
    assert "get_weather" in evidence


def test_a_fabricated_result_is_not_capable() -> None:
    """The live shape: values nobody returned, with no tool call."""
    module = _load()
    capable, reason, evidence = module.classify_probe_response(
        {
            "message": {
                "role": "assistant",
                "content": "According to the weather tool, it is partly sunny 24°C.",
            }
        }
    )
    assert capable is False
    assert reason == "confabulation"
    assert "without calling" in evidence


def test_a_call_written_as_text_is_named_honestly() -> None:
    """Live 2026-10-16: two coder models put the call in the CONTENT field.

    Not "no tool call" (that would hide that they know what to do) and not
    "confabulation" (they never claimed a result). The call simply never
    happens, because the chat API executes only structured tool_calls.
    """
    module = _load()
    capable, reason, evidence = module.classify_probe_response(
        {
            "message": {
                "role": "assistant",
                "content": '{"name": "get_weather", "arguments": {"city": "Istanbul"}}',
            }
        }
    )
    assert capable is False
    assert reason == "tool_call_as_text"
    assert "as text" in evidence


def test_a_plain_answer_without_a_call_is_not_capable() -> None:
    module = _load()
    capable, reason, _ = module.classify_probe_response(
        {"message": {"role": "assistant", "content": "I cannot check the weather."}}
    )
    assert capable is False
    assert reason == "no_tool_call"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"error": "boom"},
        {"message": None},
        {"message": {"role": "assistant", "content": "   "}},
        {"message": {"role": "assistant"}},
        "not a mapping",
    ],
)
def test_an_unproven_answer_is_never_recorded(payload: Any) -> None:
    """``None`` means 'proves nothing' — the gate must keep the declaration."""
    module = _load()
    capable, _reason, _evidence = module.classify_probe_response(payload)
    assert capable is None


# --------------------------------------------------------------- the loop


class _Model:
    def __init__(self, name: str, capabilities: tuple[str, ...], digest: str = "") -> None:
        self.name = name
        self.capabilities = capabilities
        self.digest = digest


class _Snapshot:
    models: tuple[_Model, ...] = (
        _Model("liar:8b", ("completion", "tools"), "sha256:liar"),
        _Model("honest:4b", ("completion", "tools"), "sha256:honest"),
        _Model("silent:8b", ("completion", "tools"), "sha256:silent"),
        _Model("chatonly:1b", ("completion",)),
    )


@pytest.fixture
def _probe_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    from jarvis.brain import ollama_inventory
    from jarvis.core import config as core_config

    module = _load()
    monkeypatch.setattr(core_config, "DATA_DIR", tmp_path)

    async def _snapshot(root: str) -> _Snapshot:
        return _Snapshot()

    monkeypatch.setattr(ollama_inventory, "cached_snapshot", _snapshot)

    answers: dict[str, tuple[bool | None, str, str]] = {
        "liar:8b": (False, "confabulation", "stated a result without calling"),
        "honest:4b": (True, "tool_calls", "called get_weather"),
        # An attempt that proved nothing: it must not gate, but it must be
        # visible in the audit — "tried and learned nothing" is not "never tried".
        "silent:8b": (None, "empty_reply", ""),
    }
    seen: list[str] = []

    async def _probe(root: str, model: str) -> tuple[bool | None, str, str]:
        seen.append(model)
        return answers[model]

    monkeypatch.setattr(module, "_probe_one", _probe)
    module._seen = seen  # type: ignore[attr-defined]
    return module


@pytest.mark.asyncio
async def test_only_measured_verdicts_are_recorded(_probe_env: ModuleType) -> None:
    from jarvis.brain import tool_probe_store as store

    check = await _probe_env._tool_probe("http://127.0.0.1:11434")

    # A model that declares no tools was never probed: no cost, no verdict.
    assert _probe_env._seen == ["liar:8b", "honest:4b", "silent:8b"]
    assert store.verdict_for("ollama", "liar:8b") is False
    assert store.verdict_for("ollama", "honest:4b") is True
    assert store.verdict_for("ollama", "chatonly:1b") is None
    assert store.reason_for("ollama", "liar:8b") == "confabulation"
    # The unproven attempt is audited but gates nothing.
    assert store.verdict_for("ollama", "silent:8b") is None
    assert store.entries()["ollama/silent:8b"]["capable"] is None
    assert store.reason_for("ollama", "silent:8b") == "empty_reply"
    # WARN, not FAIL: a model that overstates itself is a normal download and
    # the gate now handles it — the exit code is for a broken install.
    assert check.status == _probe_env.WARN
    assert "liar:8b" in check.detail
    assert "could not be measured" in check.detail
    assert "silent:8b" in check.detail
    assert check.facts["store"].endswith("model_tool_probe.json")


@pytest.mark.asyncio
async def test_an_unreachable_server_is_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jarvis.brain import ollama_inventory

    module = _load()

    async def _boom(root: str) -> _Snapshot:
        raise RuntimeError("no server")

    monkeypatch.setattr(ollama_inventory, "cached_snapshot", _boom)

    check = await module._tool_probe("http://127.0.0.1:11434")
    assert check.status == module.WARN
    assert "did not answer" in check.detail


@pytest.mark.asyncio
async def test_no_tool_declaring_model_means_nothing_to_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jarvis.brain import ollama_inventory

    module = _load()

    class _NoTools:
        models = (_Model("chatonly:1b", ("completion",)),)

    async def _snapshot(root: str) -> _NoTools:
        return _NoTools()

    monkeypatch.setattr(ollama_inventory, "cached_snapshot", _snapshot)

    check = await module._tool_probe("http://127.0.0.1:11434")
    assert check.status == module.WARN
    assert "nothing to measure" in check.detail


# ------------------------------------------------------ the context-fit check


class _FitModel:
    def __init__(
        self, name: str, size_gb: float, context_length: int, parameters: str = ""
    ) -> None:
        self.name = name
        self.size_bytes = int(size_gb * (1024**3))
        self.context_length = context_length
        self.parameters = parameters


def _fit_env(monkeypatch: pytest.MonkeyPatch, models: tuple[_FitModel, ...], accel: float):
    from jarvis.brain import ollama_inventory
    from jarvis.hardware import detection

    module = _load()
    monkeypatch.setattr(detection, "usable_accelerator_gb", lambda: (accel, "test probe"))

    class _Snapshot:
        pass

    # A class body does not close over the enclosing function's names, so the
    # models are attached after creation.
    _Snapshot.models = models

    async def _snapshot(root: str) -> _Snapshot:
        return _Snapshot()

    monkeypatch.setattr(ollama_inventory, "cached_snapshot", _snapshot)
    return module


@pytest.mark.asyncio
async def test_a_download_that_asks_for_more_than_the_card_holds_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live shape: 4.9 GB, native 131072 tokens, no num_ctx, 8 GB card."""
    module = _fit_env(
        monkeypatch,
        (
            _FitModel("risky:8b", 4.9, 131_072),
            _FitModel("capped:8b", 4.9, 131_072, "num_ctx 16384"),
            _FitModel("small:1b", 0.5, 32_768),
        ),
        accel=8.0,
    )

    check = await module._context_fit("http://127.0.0.1:11434")

    assert check.status == module.WARN
    assert "risky:8b" in check.detail
    # The capped variant is the FIX, not a risk; the small model cannot exhaust
    # the card by itself.
    assert "capped:8b" not in check.detail
    assert "small:1b" not in check.detail
    assert check.facts["at_risk"] == [
        {"model": "risky:8b", "size_gb": 4.9, "native_context": 131_072}
    ]
    assert check.facts["capped_by_num_ctx"] == ["capped:8b"]


@pytest.mark.asyncio
async def test_a_capped_install_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _fit_env(
        monkeypatch,
        (_FitModel("capped:8b", 4.9, 131_072, "num_ctx 16384"),),
        accel=8.0,
    )

    check = await module._context_fit("http://127.0.0.1:11434")

    assert check.status == module.OK
    assert check.facts["at_risk"] == []


@pytest.mark.asyncio
async def test_no_readable_accelerator_stands_the_check_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a memory figure there is nothing to compare — say so, never guess."""
    module = _fit_env(monkeypatch, (), accel=0.0)

    check = await module._context_fit("http://127.0.0.1:11434")

    assert check.status == module.WARN
    assert "Not checked" in check.detail
