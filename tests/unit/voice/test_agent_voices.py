"""Agent voices: every mapped id must exist in the product's own catalogue."""
from __future__ import annotations

from jarvis.voice.agent_voices import (
    AGENT_VOICES,
    FEMININE,
    MASCULINE,
    agent_voice,
    voice_for,
    voice_map,
)


def test_every_mapped_id_exists_in_the_curated_catalogue() -> None:
    """The cross-check that stops an invented voice from ever shipping."""
    from jarvis.plugins.tts.curated_catalog import voice_gender

    for agent, voice in AGENT_VOICES.items():
        tagged = voice_gender(voice.voice_id)
        if tagged is None:
            continue  # a family whose ids the catalogue does not tag yet
        assert tagged == voice.gender, (
            f"{agent}: {voice.voice_id} is tagged {tagged}, mapped as {voice.gender}"
        )


def test_every_agent_states_a_register_and_a_reason() -> None:
    for agent, voice in AGENT_VOICES.items():
        assert voice.agent == agent
        assert voice.voice_id.strip() and voice.provider.strip()
        assert voice.register.strip()
        assert len(voice.why.strip()) > 30, f"{agent} has no real justification"
        assert voice.gender in (MASCULINE, FEMININE)


def test_an_unknown_agent_has_no_voice() -> None:
    assert agent_voice("nobody") is None
    assert voice_for("nobody") is None


def test_the_mapping_is_returned_as_is_when_availability_is_unknown() -> None:
    mapped = voice_for("morpheus")
    assert mapped is not None and mapped.voice_id == AGENT_VOICES["morpheus"].voice_id


def test_a_missing_family_degrades_by_register_not_to_silence() -> None:
    degraded = voice_for("morpheus", available_providers=["piper-local"])

    assert degraded is not None
    assert degraded.provider == "piper-local"
    assert degraded.gender == MASCULINE  # the register survives
    assert "degraded" in degraded.why


def test_nothing_at_all_means_no_voice_rather_than_a_lie() -> None:
    assert voice_for("morpheus", available_providers=["some-other-family"]) is None


def test_the_full_map_covers_every_agent() -> None:
    everything = voice_map()
    assert set(everything) == set(AGENT_VOICES)
    for row in everything.values():
        assert row["voice_id"] and row["provider"] and row["why"]
