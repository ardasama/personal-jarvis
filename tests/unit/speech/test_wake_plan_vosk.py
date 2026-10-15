"""resolve_wake_plan: the any-word vosk_kws engine slots into the chain.

Chain contract (design spec 2026-07-05): custom_onnx (matching file) →
pretrained OWW (known phrase) → **vosk_kws (any phrase, per-language model)**
→ stt_match (fallback) → none/hotkey. vosk_kws must never require local
Whisper, and a missing vosk package or model falls through gracefully.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.speech.wake_constants import resolve_vosk_model_path, resolve_vosk_model_paths
from jarvis.speech.wake_phrase import resolve_wake_plan


@dataclass
class _FakeTTS:
    name: str = "fake-tts"
    supports_streaming: bool = True

    async def synthesize(
        self, text: str, voice: str | None = None, language_code: str | None = None
    ) -> AsyncIterator:
        if False:  # pragma: no cover
            yield


def _cfg(phrase: str = "Hey Nova", engine: str = "auto", custom: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        phrase=phrase,
        engine=engine,
        custom_model_path=custom,
        sensitivity=0.5,
        fuzzy_match_ratio=0.8,
    )


@pytest.fixture()
def vosk_model_dir(tmp_path, monkeypatch) -> Path:
    """A minimal on-disk layout resolve_vosk_model_path accepts (am/ subdir)."""
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    model = tmp_path / "wake_models" / "vosk" / "de" / "vosk-model-small-de-0.15"
    (model / "am").mkdir(parents=True)
    return model


def test_resolve_vosk_model_path_finds_language_and_auto(vosk_model_dir) -> None:
    assert resolve_vosk_model_path("de") == str(vosk_model_dir)
    assert resolve_vosk_model_path("de-DE") == str(vosk_model_dir)
    # auto/None fall back to the first installed language folder
    assert resolve_vosk_model_path("auto") == str(vosk_model_dir)
    assert resolve_vosk_model_path(None) == str(vosk_model_dir)
    # a language without a model resolves to nothing
    assert resolve_vosk_model_path("es") is None


def test_auto_picks_vosk_for_arbitrary_phrase(vosk_model_dir) -> None:
    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=True, language="de", vosk_available=True
    )
    assert plan.engine == "vosk_kws"
    assert plan.vosk_model_path == str(vosk_model_dir)
    assert plan.needs_local_whisper is False
    assert plan.wake_available is True
    assert plan.verify_prefix is False  # the provider's own confirm handles it


def test_jarvis_phrase_runs_on_vosk_like_any_other_word(vosk_model_dir) -> None:
    # Design 2026-07-07: no bundled model exists — "Hey Jarvis" is served by
    # the same any-word vosk engine as every other phrase.
    plan = resolve_wake_plan(
        _cfg(phrase="Hey Jarvis"),
        local_whisper_available=True,
        language="de",
        vosk_available=True,
    )
    assert plan.engine == "vosk_kws"


def test_explicit_vosk_engine_forces_vosk(vosk_model_dir) -> None:
    plan = resolve_wake_plan(
        _cfg(phrase="Hey Jarvis", engine="vosk_kws"),
        local_whisper_available=True,
        language="de",
        vosk_available=True,
    )
    assert plan.engine == "vosk_kws"


def test_no_vosk_package_falls_back_to_stt_match(vosk_model_dir) -> None:
    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=True, language="de", vosk_available=False
    )
    assert plan.engine == "stt_match"


def test_no_model_for_language_falls_back_to_stt_match(vosk_model_dir) -> None:
    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=True, language="es", vosk_available=True
    )
    assert plan.engine == "stt_match"


def test_stale_custom_model_resolves_to_vosk(vosk_model_dir, tmp_path) -> None:
    # A leftover hey_nico.onnx must not keep the NEW phrase on the weak path.
    stale = tmp_path / "hey_nico.onnx"
    stale.write_bytes(b"onnx")
    plan = resolve_wake_plan(
        _cfg(custom=str(stale)),
        local_whisper_available=True,
        language="de",
        vosk_available=True,
    )
    assert plan.engine == "vosk_kws"


def test_matching_custom_model_still_wins(vosk_model_dir, tmp_path) -> None:
    own = tmp_path / "hey_nova.onnx"
    own.write_bytes(b"onnx")
    plan = resolve_wake_plan(
        _cfg(custom=str(own)),
        local_whisper_available=True,
        language="de",
        vosk_available=True,
    )
    assert plan.engine == "custom_onnx"


def test_no_vosk_no_whisper_is_honest_wake_off(vosk_model_dir) -> None:
    plan = resolve_wake_plan(
        _cfg(),
        local_whisper_available=False,
        language="es",  # no model for es in the fixture
        vosk_available=True,
    )
    assert plan.engine == "none"
    assert plan.wake_available is False


# --------------------------------------------------------------------------
# Pipeline live-apply: a vosk plan must actually ARM the detector
# --------------------------------------------------------------------------


def test_set_wake_plan_vosk_keeps_unverified_candidates_internal(
    vosk_model_dir,
) -> None:
    """Live-apply must not expose noisy grammar hits to the visible overlay."""
    from jarvis.core.bus import EventBus
    from jarvis.plugins.wake.vosk_kws_provider import VoskKwsProvider
    from jarvis.speech.pipeline import SpeechPipeline

    pipe = SpeechPipeline(
        tts=_FakeTTS(), bus=EventBus(),
        enable_openwakeword=False, enable_whisper_wake=False,
        enable_local_whisper=False, config=None,
    )
    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=False, language="de", vosk_available=True
    )
    assert plan.engine == "vosk_kws"
    pipe.set_wake_plan(plan)

    assert isinstance(pipe._wake, VoskKwsProvider)
    assert not hasattr(pipe._wake, "_on_candidate")


def test_constructor_wake_plan_keeps_unverified_candidates_internal(
    vosk_model_dir,
) -> None:
    """The initial construction path has the same confirmed-wake boundary."""
    from jarvis.core.bus import EventBus
    from jarvis.plugins.wake.vosk_kws_provider import VoskKwsProvider
    from jarvis.speech.pipeline import SpeechPipeline

    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=False, language="de", vosk_available=True
    )
    assert plan.engine == "vosk_kws"

    pipe = SpeechPipeline(
        tts=_FakeTTS(), bus=EventBus(),
        enable_openwakeword=False, enable_whisper_wake=False,
        enable_local_whisper=False, config=None,
        wake_plan=plan,
    )

    assert isinstance(pipe._wake, VoskKwsProvider)
    assert not hasattr(pipe._wake, "_on_candidate")


def test_set_wake_plan_vosk_arms_the_provider(vosk_model_dir) -> None:
    # Regression guard for the 2026-07-06 live finding: the plan resolved to
    # vosk_kws but the detector flag stayed off (OWW=off in the ready log), so
    # the wake was silently dead. The vosk provider rides the OWW slot/loop —
    # arming it must flip the flag on.
    from jarvis.plugins.wake.vosk_kws_provider import VoskKwsProvider
    from jarvis.speech.pipeline import SpeechPipeline

    pipe = SpeechPipeline(
        tts=_FakeTTS(), bus=None,
        enable_openwakeword=False, enable_whisper_wake=False,
        enable_local_whisper=False, config=None,
    )
    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=False, language="de", vosk_available=True
    )
    assert plan.engine == "vosk_kws"
    pipe.set_wake_plan(plan)

    assert isinstance(pipe._wake, VoskKwsProvider)
    assert pipe._openwakeword_enabled is True  # the detector loop is armed
    assert pipe._whisper_wake_enabled is False
    assert pipe._wake_reload_event.is_set()


# --------------------------------------------------------------------------
# An unreadable model folder must degrade, never crash the boot path
# --------------------------------------------------------------------------
# Forensic 2026-10-15 (live boot log): ``data\wake_models\vosk\en`` raised
# ``PermissionError: [WinError 5] Access is denied`` inside ``_vosk_model_dir``.
# Windows can refuse to ENUMERATE a folder that exists and whose parent is
# readable (a stray deny ACE, a concurrent extraction, an AV/EDR lock). The
# exception propagated out of ``resolve_vosk_model_path`` and ``resolve_wake_plan``
# into ``desktop_app._start_speech_and_orb``, so the wake-model gate timed out
# ("Heavy backend: wake-model gate timed out (12 s)") and the voice-ready
# watchdog fired at 45 s -- one unreadable folder killed the whole wake plan.


def _deny_listing(monkeypatch, denied_name: str) -> None:
    """Make ``Path.iterdir()`` raise PermissionError for ONE directory name.

    Only the named directory is affected; every other path keeps the real
    ``iterdir``, so the surrounding layout still works.
    """
    real_iterdir = Path.iterdir

    def _iterdir(self: Path):
        if self.name == denied_name:
            raise PermissionError(5, "Access is denied", str(self))
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", _iterdir)


def _make_language_dir(tmp_path, language: str) -> Path:
    """Create an empty language folder in the Vosk store; returns the store root."""
    store = tmp_path / "wake_models" / "vosk"
    (store / language).mkdir(parents=True)
    return store


def test_unreadable_language_folder_resolves_to_none(tmp_path, monkeypatch) -> None:
    """An unlistable language folder means "no model here", not a crash."""
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    _make_language_dir(tmp_path, "en")
    _deny_listing(monkeypatch, "en")

    assert resolve_vosk_model_path("en") is None


def test_unreadable_language_folder_falls_through_to_stt_match(
    tmp_path, monkeypatch
) -> None:
    """The wake plan must fall through to the next engine, as the chain promises.

    A **missing** model already falls through (see
    ``test_no_model_for_language_falls_back_to_stt_match``); an unreadable one must
    behave the same instead of raising into the boot path.
    """
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    _make_language_dir(tmp_path, "en")
    _deny_listing(monkeypatch, "en")

    plan = resolve_wake_plan(
        _cfg(), local_whisper_available=True, language="en", vosk_available=True
    )

    assert plan.engine == "stt_match"
    assert plan.vosk_model_path is None


def test_unreadable_models_root_yields_no_models(tmp_path, monkeypatch) -> None:
    """An unlistable store root must yield no models, not raise."""
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    _make_language_dir(tmp_path, "en")
    _deny_listing(monkeypatch, "vosk")

    assert resolve_vosk_model_paths("en") == []
    assert resolve_vosk_model_path("auto") is None


def test_unreadable_folder_is_logged_with_its_cause(tmp_path, monkeypatch, caplog) -> None:
    """The degradation is logged with the folder and the OS error (AP-30).

    A swallowed exception with no reason is exactly what the project forbids:
    the operator must be able to see WHY the wake engine fell through.
    """
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    _make_language_dir(tmp_path, "en")
    _deny_listing(monkeypatch, "en")

    with caplog.at_level("WARNING", logger="jarvis.speech.wake_constants"):
        assert resolve_vosk_model_path("en") is None

    assert caplog.records, "an unlistable model folder must be logged"
    message = caplog.records[0].getMessage()
    assert "en" in message
    assert "PermissionError" in message

