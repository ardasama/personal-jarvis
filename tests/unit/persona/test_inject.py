"""Injection: the ordering contract, verified offline."""
from __future__ import annotations

from jarvis.persona.inject import (
    HOUSE_LIMITS,
    block_for_turn,
    character_block,
    limits_block,
    merge_into_prompt,
)


def test_a_spoken_turn_gets_the_short_form_by_default() -> None:
    short = character_block(task="teach", channel="voice")
    long_form = character_block(task="teach", channel="text")

    assert "\n" not in short
    assert len(short) < len(long_form)
    assert long_form.startswith("## Character:")


def test_the_caller_may_override_the_length() -> None:
    assert "\n" in character_block(task="teach", channel="voice", short=False)
    assert "\n" not in character_block(task="teach", channel="text", short=True)


def test_the_ordering_is_identity_then_manner_then_limits() -> None:
    merged = merge_into_prompt(soul="## Who\nI am Jarvis.", character="## Character: x")

    identity_at = merged.index("I am Jarvis.")
    manner_at = merged.index("## Character: x")
    limits_at = merged.index("## Non-negotiable limits")

    assert identity_at < manner_at < limits_at


def test_the_limits_are_present_even_with_nothing_else() -> None:
    merged = merge_into_prompt()
    assert "## Non-negotiable limits" in merged
    for rule in HOUSE_LIMITS:
        assert rule in merged


def test_a_character_never_widens_a_limit() -> None:
    """The spoken block is tiny; the limits are still unconditional."""
    spoken = block_for_turn(soul="", task="incident", channel="voice")
    full = block_for_turn(soul="", task="incident", channel="text")

    for merged in (spoken, full):
        assert all(rule in merged for rule in HOUSE_LIMITS)
    assert len(spoken) < len(full)


def test_the_block_is_deterministic_for_the_same_moment() -> None:
    first = block_for_turn(soul="## Who\nI am Jarvis.", text="acil, sunucu çöktü", channel="voice")
    second = block_for_turn(soul="## Who\nI am Jarvis.", text="acil, sunucu çöktü", channel="voice")

    assert first == second


def test_an_unknown_moment_still_produces_a_usable_block() -> None:
    merged = block_for_turn(soul="", task="wizardry", channel="voice")

    assert "As " in merged  # a character was still composed
    assert "## Non-negotiable limits" in merged


def test_the_limits_block_is_stable_and_numbered_by_bullets() -> None:
    text = limits_block()
    assert text.count("\n- ") == len(HOUSE_LIMITS)
