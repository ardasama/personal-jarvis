"""Injection: the composed character, laid into the prompt WITHOUT replacing SOUL.

The ordering is the contract, and it is not cosmetic:

1. **SOUL first** - who Jarvis IS (one stable self, the one that learns).
2. **Character second** - how it behaves in THIS moment (composed from traits).
3. **Limits last** - the non-negotiables, so nothing above can loosen them.

The character can never widen a limit: the catalogue guarantees that adding an
ingredient only ever GROWS the "never" list, and this module appends the house
limits unconditionally - even when the spoken block is one line long.

Voice turns get the short form, written turns the full one, from the same
recipe, so the character never changes shape - only how much instruction the
model receives.

The observer stays invisible: nothing here surfaces a learning process, a
reflection or a meta-comment. The front stage carries one coherent character.
"""
from __future__ import annotations

from typing import Any

#: Always present, whatever the moment. Written once, appended last.
HOUSE_LIMITS: tuple[str, ...] = (
    "Never delete or overwrite the person's data without a uniquely named backup.",
    "Never reveal, print or store a credential.",
    "Never present an unverified result as a verified one: name the blocker instead.",
)


def character_block(
    *,
    text: str = "",
    task: str | None = None,
    audience: str | None = None,
    urgency: str | None = None,
    reversibility: str | None = None,
    channel: str | None = None,
    language: str | None = None,
    short: bool | None = None,
) -> str:
    """The character directive for this moment.

    ``short`` defaults to "this is a spoken turn": a voice turn cannot carry a
    page of instruction, and the same recipe already knows how to say itself in
    one line.
    """
    from jarvis.persona.situation import persona_for  # noqa: PLC0415 - keeps this file light

    persona, _selection = persona_for(
        text=text,
        task=task,
        audience=audience,
        urgency=urgency,
        reversibility=reversibility,
        channel=channel,
        language=language,
    )
    is_voice = (channel or "").strip().lower() == "voice"
    use_short = is_voice if short is None else bool(short)
    return persona.describe(short=use_short)


def limits_block() -> str:
    """The non-negotiables, as the last word of the prompt."""
    return "## Non-negotiable limits\n" + "\n".join(f"- {rule}" for rule in HOUSE_LIMITS)


def merge_into_prompt(*, soul: str = "", character: str = "") -> str:
    """SOUL (identity) -> character (manner) -> limits (last). Always that order.

    An empty SOUL is allowed (a test or a young install); the limits are not -
    they are appended even when both inputs are empty, because a prompt without
    them is the one case where the character could act unchained.
    """
    parts: list[str] = []
    if str(soul or "").strip():
        parts.append(str(soul).strip())
    if str(character or "").strip():
        parts.append(str(character).strip())
    parts.append(limits_block())
    return "\n\n".join(parts)


def block_for_turn(soul: str = "", **signals: Any) -> str:
    """The whole prompt addition for one turn: identity, manner, limits.

    This is the call the brain path makes. It analyses the moment, composes the
    character, and returns the merged block - never a bare character, so the
    limits can never be omitted by a caller in a hurry.
    """
    return merge_into_prompt(soul=soul, character=character_block(**signals))


__all__ = [
    "HOUSE_LIMITS",
    "block_for_turn",
    "character_block",
    "limits_block",
    "merge_into_prompt",
]
