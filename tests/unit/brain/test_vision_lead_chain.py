"""Image turns must lead with a live vision FAST model, not the Tool Model.

Live 2026-08-31 17:06: prefer_tool_model hoisted Vertex gemini-3.7-flash.
Five providers failed (schema / 402 / 401 / 429 retries) and grok-4.6
answered after 20 s. A look turn leads with the router-tier vision model.
"""

from __future__ import annotations

from types import SimpleNamespace

from jarvis.brain.manager import BrainManager


class _Vision:
    supports_vision = True


class _Blind:
    supports_vision = False


def _mgr(*, active: str = "grok") -> BrainManager:
    m = BrainManager.__new__(BrainManager)
    m._active_name = active
    m._dead_providers = set()
    m._brain_cache = {}
    m._config = SimpleNamespace(
        brain=SimpleNamespace(
            router=SimpleNamespace(
                provider="grok",
                model="grok-4.20-0309-non-reasoning",
            )
        ),
        screen_context=SimpleNamespace(vision_provider="", vision_model=""),
    )
    brains = {
        "grok": _Vision(),
        "vertex": _Vision(),
        "openrouter": _Vision(),
        "claude-api": _Vision(),
        "codex": _Blind(),
    }

    def _get_brain(provider: str, model: str | None = None, **kwargs: object) -> object:
        return brains[provider]

    def _fast_model(provider: str) -> str:
        return {"grok": "grok-4.3", "vertex": "gemini-3.5-flash"}.get(provider, "fast")

    m._get_brain = _get_brain  # type: ignore[method-assign]
    m._fast_model = _fast_model  # type: ignore[method-assign]
    return m


def test_image_turn_leads_with_the_router_vision_model() -> None:
    m = _mgr()
    chain = [
        ("vertex", "gemini-3.7-flash"),
        ("openrouter", "google/gemini-3.5-flash"),
        ("claude-api", "claude-opus-4-8"),
        ("grok", "grok-4.6"),
    ]
    led = m._lead_vision_chain(chain)
    assert led[0] == ("grok", "grok-4.20-0309-non-reasoning")


def test_chat_primary_does_not_outrank_the_router() -> None:
    """Live 2026-08-31 19:38: primary=openrouter, router=grok.

    Ranking by ``_active_name`` put OpenRouter first (402, no credits),
    then Vertex sat 20.5 s. The router vision model must still lead.
    """
    m = _mgr(active="openrouter")
    chain = [
        ("openrouter", "google/gemini-3.5-flash"),
        ("vertex", "gemini-3.7-flash"),
        ("grok", "grok-4.6"),
    ]
    led = m._lead_vision_chain(chain)
    assert led[0] == ("grok", "grok-4.20-0309-non-reasoning")
    assert led[1][0] != "grok"


def test_dead_providers_are_dropped_from_the_look_chain() -> None:
    m = _mgr(active="openrouter")
    m._dead_providers.add("openrouter")
    led = m._lead_vision_chain(
        [
            ("openrouter", "google/gemini-3.5-flash"),
            ("vertex", "gemini-3.7-flash"),
            ("grok", "grok-4.6"),
        ]
    )
    assert led[0] == ("grok", "grok-4.20-0309-non-reasoning")
    assert all(item[0] != "openrouter" for item in led)


def test_blind_providers_stay_in_the_tail() -> None:
    m = _mgr(active="codex")
    led = m._lead_vision_chain([("codex", "gpt-5.5"), ("grok", "grok-4.6")])
    assert led[0][0] == "grok"
    assert led[-1][0] == "codex"


def test_explicit_screen_model_precedes_cloud_router_only_for_image_turns() -> None:
    m = _mgr()
    m._config.screen_context.vision_provider = "ollama"
    m._config.screen_context.vision_model = "qwen3.5:4b-8k"
    checked: list[tuple[str, str | None]] = []

    def brain(provider: str, model: str | None = None) -> object:
        checked.append((provider, model))
        return _Vision()

    m._get_brain = brain  # type: ignore[method-assign]
    chain = [("grok", "grok-4.6"), ("openrouter", "free-model")]
    led = m._lead_vision_chain(chain)
    assert led[0] == ("ollama", "qwen3.5:4b-8k")
    assert led[1] == ("grok", "grok-4.20-0309-non-reasoning")
    assert checked[0] == ("ollama", "qwen3.5:4b-8k")
    assert led.count(("ollama", "qwen3.5:4b-8k")) == 1
    # An explicitly selected turn has its own model/credential.
    assert m._lead_vision_chain(chain, include_screen_model=False)[0][0] == "grok"


def test_screen_model_does_not_activate_when_incomplete_or_unavailable() -> None:
    m = _mgr()
    normal = [("grok", "grok-4.6"), ("codex", "gpt-5.5")]
    m._config.screen_context.vision_provider = "ollama"
    assert m._lead_vision_chain(normal)[0][0] == "grok"
    m._config.screen_context.vision_model = "text-only"
    m._get_brain = (  # type: ignore[method-assign]
        lambda provider, model=None: _Blind() if provider == "ollama" else _Vision()
    )
    assert m._lead_vision_chain(normal)[0][0] == "grok"
    m._config.screen_context.vision_model = "qwen3.5:4b-8k"
    m._dead_providers.add("ollama")
    assert m._lead_vision_chain(normal)[0][0] == "grok"


def test_screen_model_settings_are_opt_in_and_not_agent_self_mutable() -> None:
    from jarvis.core.config import JarvisConfig, ScreenContextConfig
    from jarvis.core.self_mod.forbidden import is_forbidden

    default = JarvisConfig().screen_context
    assert default.vision_provider == ""
    assert default.vision_model == ""
    custom = ScreenContextConfig(
        vision_provider="ollama", vision_model="qwen3.5:4b-8k"
    )
    assert custom.vision_provider == "ollama"
    assert custom.vision_model == "qwen3.5:4b-8k"
    assert is_forbidden("screen_context.vision_provider")
    assert is_forbidden("screen_context.vision_model")


def test_screen_model_deduplicates_a_provider_already_in_chain() -> None:
    m = _mgr()
    m._config.screen_context.vision_provider = "ollama"
    m._config.screen_context.vision_model = "qwen3.5:4b-8k"
    m._get_brain = lambda provider, model=None: _Vision()  # type: ignore[method-assign]
    led = m._lead_vision_chain([("ollama", "deepseek-r1:8b"), ("grok", "grok-4.6")])
    assert led[0] == ("ollama", "qwen3.5:4b-8k")
    assert len([row for row in led if row[0] == "ollama"]) == 1
