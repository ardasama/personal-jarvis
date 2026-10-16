"""Tests for the Flash-Brain's key-aware ``follow_brain`` fallback (AP-22).

When ``brain.primary`` points at a provider the Flash-Brain has no adapter
for (openrouter, claude_api), ``_build_flash_provider`` used to fall back to
a hardcoded literal ``"gemini"`` — bricking the tier for any downloader whose
only configured key is for a different provider. The fallback must instead
pick the first REGISTRY family with a usable credential.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from jarvis.brain.factory import _build_flash_provider, _pick_keyed_flash_fallback
from tests.unit.brain.test_ack_brain.conftest import make_ack_config


@pytest.fixture(autouse=True)
def _hermetic_health_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the pick deterministic.

    The real ledger (``data/state/provider_health.json``) holds THIS box's own
    credential failures; a unit test must never depend on it. Tests that
    exercise the dead-key deferral override this patch explicitly.
    """
    monkeypatch.setattr(
        "jarvis.brain.provider_health_ledger.has_credential_failure",
        lambda provider=None: False,
    )


def _jcfg(*, brain_primary: str) -> SimpleNamespace:
    return SimpleNamespace(brain=SimpleNamespace(primary=brain_primary))


def test_falls_back_to_openai_when_only_openai_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """brain.primary="claude-api" has no Flash adapter; only an OpenAI key is
    configured — the fallback must resolve to "openai", never "gemini"."""

    def _fake_get_secret(key: str, env_fallback: str | None = None) -> str | None:
        return "sk-test" if key == "openai_api_key" else None

    monkeypatch.setattr("jarvis.core.config.get_secret", _fake_get_secret)

    ack_cfg = make_ack_config(provider="follow_brain")
    provider = _build_flash_provider(_jcfg(brain_primary="claude-api"), ack_cfg)

    assert ack_cfg.provider == "openai"
    assert type(provider).__name__ == "OpenAIMiniAck"


def test_falls_back_to_gemini_when_only_gemini_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_get_secret(key: str, env_fallback: str | None = None) -> str | None:
        return "gk-test" if key == "gemini_api_key" else None

    monkeypatch.setattr("jarvis.core.config.get_secret", _fake_get_secret)

    ack_cfg = make_ack_config(provider="follow_brain")
    provider = _build_flash_provider(_jcfg(brain_primary="claude-api"), ack_cfg)

    assert ack_cfg.provider == "gemini"
    assert type(provider).__name__ == "GeminiFlashAck"


def test_falls_back_to_gemini_when_only_a_realtime_scoped_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single-key install whose only credential came from the Realtime card
    must still resolve the Flash tier to that family (2026-07-21 Mac forensic:
    the strict slot scoping bricked every non-realtime brain tier)."""

    def _fake_get_secret(key: str, env_fallback: str | None = None) -> str | None:
        return "rt-test" if key == "realtime_gemini_api_key" else None

    monkeypatch.setattr("jarvis.core.config.get_secret", _fake_get_secret)

    ack_cfg = make_ack_config(provider="follow_brain")
    provider = _build_flash_provider(_jcfg(brain_primary="claude-api"), ack_cfg)

    assert ack_cfg.provider == "gemini"
    assert type(provider).__name__ == "GeminiFlashAck"


def test_falls_back_to_ollama_when_no_key_present_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama needs no credential (local endpoint) — it is the last-resort
    keyless fallback when no cloud provider has a usable key."""
    monkeypatch.setattr(
        "jarvis.core.config.get_secret", lambda key, env_fallback=None: None
    )

    ack_cfg = make_ack_config(provider="follow_brain")
    provider = _build_flash_provider(_jcfg(brain_primary="claude-api"), ack_cfg)

    assert ack_cfg.provider == "ollama"
    assert type(provider).__name__ == "OllamaFlashAck"


def test_does_not_change_ack_behavior_when_primary_has_a_flash_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When brain.primary IS a REGISTRY family, the fallback path is never
    consulted — no credential lookup happens at all."""
    called = False

    def _fail_get_secret(key: str, env_fallback: str | None = None) -> str | None:
        nonlocal called
        called = True
        return None

    monkeypatch.setattr("jarvis.core.config.get_secret", _fail_get_secret)

    ack_cfg = make_ack_config(provider="follow_brain")
    provider = _build_flash_provider(_jcfg(brain_primary="openai"), ack_cfg)

    assert ack_cfg.provider == "openai"
    assert type(provider).__name__ == "OpenAIMiniAck"
    assert called is False


def _live_jcfg(*, brain_primary: str) -> SimpleNamespace:
    """GPT-Live is the voice: the OpenAI key belongs to the voice call."""
    return SimpleNamespace(
        voice=SimpleNamespace(mode="realtime"),
        brain=SimpleNamespace(
            primary=brain_primary,
            realtime=SimpleNamespace(provider="openai-live"),
        ),
    )


def test_primary_on_the_voice_key_hands_flash_work_to_another_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mandate 2026-09-29: the GPT-Live key pays for the voice call only."""
    keys = {"openai_api_key": "sk-test", "gemini_api_key": "gk-test"}
    monkeypatch.setattr(
        "jarvis.core.config.get_secret", lambda key, env_fallback=None: keys.get(key)
    )

    ack_cfg = make_ack_config(provider="follow_brain")
    provider = _build_flash_provider(_live_jcfg(brain_primary="openai"), ack_cfg)

    assert ack_cfg.provider == "gemini"
    assert type(provider).__name__ == "GeminiFlashAck"


def test_single_voice_key_install_still_gets_a_flash_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the voice key as the only credential, flash work stays on it
    rather than on a local server that may not exist (AP-22)."""
    monkeypatch.setattr(
        "jarvis.core.config.get_secret",
        lambda key, env_fallback=None: "sk-test" if key == "openai_api_key" else None,
    )

    ack_cfg = make_ack_config(provider="follow_brain")
    _build_flash_provider(_live_jcfg(brain_primary="openai"), ack_cfg)

    assert ack_cfg.provider == "openai"


def test_pipeline_voice_keeps_following_an_openai_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a realtime voice the key is an ordinary brain key."""
    monkeypatch.setattr(
        "jarvis.core.config.get_secret", lambda key, env_fallback=None: "sk-test"
    )
    jcfg = _live_jcfg(brain_primary="openai")
    jcfg.voice.mode = "pipeline"

    ack_cfg = make_ack_config(provider="follow_brain")
    _build_flash_provider(jcfg, ack_cfg)

    assert ack_cfg.provider == "openai"


# --------------------------------------------------- the reason, said truly


def test_a_voice_key_primary_reports_the_real_reason(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Live 2026-10-16: brain.primary='gemini' (on the realtime voice key) was
    logged as "has no Flash adapter" although gemini IS in REGISTRY. The reader
    went hunting a missing adapter that never was missing."""
    keys = {"openai_api_key": "sk-test", "gemini_api_key": "gk-test"}
    monkeypatch.setattr(
        "jarvis.core.config.get_secret", lambda key, env_fallback=None: keys.get(key)
    )

    ack_cfg = make_ack_config(provider="follow_brain")
    with caplog.at_level(logging.WARNING, logger="jarvis.brain.factory"):
        _build_flash_provider(_live_jcfg(brain_primary="openai"), ack_cfg)

    assert ack_cfg.provider == "gemini"
    assert "realtime voice key" in caplog.text
    assert "has no Flash adapter" not in caplog.text


def test_a_primary_without_an_adapter_still_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """claude-api genuinely has no Flash adapter — that message must survive."""

    def _fake_get_secret(key: str, env_fallback: str | None = None) -> str | None:
        return "sk-test" if key == "openai_api_key" else None

    monkeypatch.setattr("jarvis.core.config.get_secret", _fake_get_secret)

    ack_cfg = make_ack_config(provider="follow_brain")
    with caplog.at_level(logging.WARNING, logger="jarvis.brain.factory"):
        _build_flash_provider(_jcfg(brain_primary="claude-api"), ack_cfg)

    assert ack_cfg.provider == "openai"
    assert "has no Flash adapter" in caplog.text
    assert "realtime voice key" not in caplog.text


def test_no_fallback_at_all_names_the_true_reason(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Voice-key primary and no usable credential anywhere: the disabling
    message names the voice key, not a missing adapter."""
    monkeypatch.setattr(
        "jarvis.core.config.get_secret",
        lambda key, env_fallback=None: "sk-test" if key == "openai_api_key" else None,
    )
    jcfg = _live_jcfg(brain_primary="openai")
    jcfg.voice.mode = "pipeline"  # nothing bills the voice key now
    # Make the primary genuinely adapter-less AND credential-less everywhere.
    jcfg.brain.primary = "claude-api"
    monkeypatch.setattr(
        "jarvis.brain.factory._pick_keyed_flash_fallback", lambda *a, **k: None
    )

    ack_cfg = make_ack_config(provider="follow_brain")
    with caplog.at_level(logging.WARNING, logger="jarvis.brain.factory"):
        provider = _build_flash_provider(jcfg, ack_cfg)

    assert provider is None
    assert "has no Flash adapter" in caplog.text  # the honest reason here


# ------------------------------------------------------ the dead-key deferral


def _pick_cfg(*families: str) -> SimpleNamespace:
    """An ack config exposing only ``families`` (credential slot per family)."""

    def _entry(secret: str | None) -> SimpleNamespace:
        return SimpleNamespace(api_key_secret=secret)

    every = {
        "gemini": _entry("gemini_api_key"),
        "grok": _entry("xai_api_key"),
        "openai": _entry("openai_api_key"),
        "ollama": _entry(None),
    }
    return SimpleNamespace(providers=SimpleNamespace(**{f: every[f] for f in families}))


def test_a_dead_key_family_is_skipped_for_a_working_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live 2026-10-16: flash work landed on 'grok', whose key answered
    "User not found." A family the ledger saw fail must not be picked while
    another keyed family works."""
    monkeypatch.setattr(
        "jarvis.core.config.get_provider_secret", lambda provider, *a, **k: None
    )
    keys = {"gemini_api_key": "gk-dead", "openai_api_key": "sk-live"}
    monkeypatch.setattr(
        "jarvis.core.config.get_secret", lambda key, env_fallback=None: keys.get(key)
    )
    monkeypatch.setattr(
        "jarvis.brain.provider_health_ledger.has_credential_failure",
        lambda provider=None: provider == "gemini",
    )

    pick = _pick_keyed_flash_fallback(_pick_cfg("gemini", "openai"))
    assert pick == "openai"


def test_a_dead_key_family_is_still_the_last_resort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never a silent disable: with only the failed key present (no keyless
    family configured) flash still resolves to it, so the person sees the
    failure and fixes the key in-app."""
    monkeypatch.setattr(
        "jarvis.core.config.get_provider_secret", lambda provider, *a, **k: None
    )
    monkeypatch.setattr(
        "jarvis.core.config.get_secret",
        lambda key, env_fallback=None: "gk-dead" if key == "gemini_api_key" else None,
    )
    monkeypatch.setattr(
        "jarvis.brain.provider_health_ledger.has_credential_failure",
        lambda provider=None: provider == "gemini",
    )

    pick = _pick_keyed_flash_fallback(_pick_cfg("gemini", "openai"))
    assert pick == "gemini"


def test_a_keyless_local_family_outranks_a_dead_cloud_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local server needs no credential, so it answers when the cloud key is
    known-dead — the honest order (live shape: gemini 401, ollama up)."""
    monkeypatch.setattr(
        "jarvis.core.config.get_provider_secret", lambda provider, *a, **k: None
    )
    monkeypatch.setattr(
        "jarvis.core.config.get_secret",
        lambda key, env_fallback=None: "gk-dead" if key == "gemini_api_key" else None,
    )
    monkeypatch.setattr(
        "jarvis.brain.provider_health_ledger.has_credential_failure",
        lambda provider=None: provider == "gemini",
    )

    pick = _pick_keyed_flash_fallback(_pick_cfg("gemini", "openai", "ollama"))
    assert pick == "ollama"


def test_a_working_key_is_untouched_by_the_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "jarvis.core.config.get_provider_secret", lambda provider, *a, **k: None
    )
    monkeypatch.setattr(
        "jarvis.core.config.get_secret",
        lambda key, env_fallback=None: "gk-live" if key == "gemini_api_key" else None,
    )
    monkeypatch.setattr(
        "jarvis.brain.provider_health_ledger.has_credential_failure",
        lambda provider=None: False,
    )

    assert _pick_keyed_flash_fallback(_pick_cfg("gemini", "openai")) == "gemini"
