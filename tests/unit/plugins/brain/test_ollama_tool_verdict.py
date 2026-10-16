"""A MEASURED tool verdict outranks the model's own declaration (AP-21).

Live 2026-10-16: ``deepseek-r1:8b`` declared ``tools``, never emitted a tool
call, fabricated a result and took ~85 s per turn; the control
``qwen3.5:4b`` called the tool correctly. ``/api/show`` cannot tell the two
apart — a recorded behavioural verdict can. No verdict recorded means the
declaration stands (fail-open, AP-22).
"""
from __future__ import annotations

import pytest

from jarvis.core.config import JarvisConfig
from jarvis.plugins.brain.ollama import OllamaBrain
from tests.fakes.provider_config import install_provider_config


@pytest.fixture(autouse=True)
def _host_config(monkeypatch: pytest.MonkeyPatch) -> None:
    install_provider_config(monkeypatch, JarvisConfig())


def _verdict(monkeypatch: pytest.MonkeyPatch, value: bool | None) -> None:
    monkeypatch.setattr(
        "jarvis.brain.tool_probe_store.verdict_for",
        lambda provider, model, **kwargs: value,
    )


def _brain(model: str = "some-model:latest") -> OllamaBrain:
    return OllamaBrain(model)


def test_no_verdict_keeps_the_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    _verdict(monkeypatch, None)
    brain = _brain()
    assert brain.supports_tools is True
    assert brain.can_call_tools() is True


def test_a_measured_no_overrides_the_instances_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _verdict(monkeypatch, False)
    brain = _brain("deepseek-r1:8b")
    assert brain.supports_tools is False
    assert brain.can_call_tools() is False


def test_a_measured_yes_lifts_a_withheld_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that really calls tools is not punished for a silent catalog."""
    _verdict(monkeypatch, True)
    brain = _brain()
    assert brain._tool_capability("m", False) is True


def test_the_verdict_decides_both_ways(monkeypatch: pytest.MonkeyPatch) -> None:
    brain = _brain()
    _verdict(monkeypatch, False)
    assert brain._tool_capability("m", True) is False
    _verdict(monkeypatch, True)
    assert brain._tool_capability("m", False) is True
    _verdict(monkeypatch, None)
    assert brain._tool_capability("m", True) is True
    assert brain._tool_capability("m", False) is False


def test_a_broken_store_keeps_the_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(provider: str, model: str, **kwargs: object) -> bool | None:
        raise RuntimeError("store gone")

    monkeypatch.setattr("jarvis.brain.tool_probe_store.verdict_for", _boom)
    brain = _brain()
    assert brain._tool_capability("m", True) is True


@pytest.mark.asyncio
async def test_an_explicit_pick_that_measured_no_is_refused_honestly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declared ``tools`` capability is there; the measurement says no."""
    _verdict(monkeypatch, False)
    brain = _brain("deepseek-r1:8b")
    monkeypatch.setattr(
        OllamaBrain, "_resolve_root", lambda self: "http://127.0.0.1:11434"
    )

    async def _caps(self: OllamaBrain, name: str, root: str) -> set[str]:
        return {"completion", "tools"}

    monkeypatch.setattr(OllamaBrain, "_capabilities", _caps)

    with pytest.raises(RuntimeError, match="does not support tools"):
        await brain._resolve_model(need_tools=True)


@pytest.mark.asyncio
async def test_an_explicit_pick_with_no_verdict_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _verdict(monkeypatch, None)
    brain = _brain("qwen3.5:4b")
    monkeypatch.setattr(
        OllamaBrain, "_resolve_root", lambda self: "http://127.0.0.1:11434"
    )

    async def _caps(self: OllamaBrain, name: str, root: str) -> set[str]:
        return {"completion", "tools"}

    monkeypatch.setattr(OllamaBrain, "_capabilities", _caps)

    assert await brain._resolve_model(need_tools=True) == "qwen3.5:4b"
    assert brain.supports_tools is True
