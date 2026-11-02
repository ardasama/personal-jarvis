"""Contract checks for explicitly selected Turkish output language.

These are local, deterministic tests. No user settings, credentials, microphone,
network calls or runtime model provider are exercised.
"""
from __future__ import annotations

from jarvis.brain.manager import (
    BrainManager,
    SUPPORTED_REPLY_LANGUAGES,
    normalize_reply_language,
)
from jarvis.core.turn_language import (
    detect_language_request,
    normalize_language_tag,
    resolve_output_language,
    validate_output_language,
)


def test_turkish_pin_supported_through_frontend_backend_contract() -> None:
    assert "tr" in SUPPORTED_REPLY_LANGUAGES
    assert normalize_reply_language(" TR ") == "tr"
    assert normalize_language_tag("tr-TR") == "tr"
    assert resolve_output_language("tr", "de-DE", "Bitte antworte auf Deutsch") == "tr"


def test_turkish_selection_updates_live_brain_pin_without_boot() -> None:
    brain = object.__new__(BrainManager)
    brain.set_reply_language("tr")
    assert brain.reply_language == "tr"
    assert "Turkish" in brain._reply_language_directive()


def test_explicit_turkish_request_and_output_validation_are_safe() -> None:
    assert detect_language_request("Please reply in Turkish") == "tr"
    # A sentence the three-language classifier cannot confidently label
    # must not be blocked simply because the user explicitly pinned Turkish.
    result = validate_output_language("Merhaba, size nasıl yardımcı olabilirim?", resolved_language="tr")  # i18n-allow: Turkish sample reply
    assert not result.should_block
