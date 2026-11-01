"""Situation: read the moment, then choose the ingredients.

The character catalogue knows how to BUILD a person; this decides WHICH person
the moment calls for. It is deterministic on purpose - a model may play the
character, never choose it - and it explains itself: every ingredient carries
the reason it was picked, so a wrong character can be argued with instead of
guessed at.

Signals it reads: what the task is, who is listening, how urgent it is, whether
it can be undone, which channel carries it, and in which language. Anything
unknown falls back to the everyday assistant - never to a specialist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TASKS: tuple[str, ...] = (
    "chat", "question", "code", "research", "review", "decide", "teach", "incident",
)
AUDIENCES: tuple[str, ...] = ("owner", "peer", "agent", "external")
URGENCIES: tuple[str, ...] = ("low", "normal", "high")
CHANNELS: tuple[str, ...] = ("voice", "text")

#: Keyword cues so a caller may pass only the text. Deliberately small and
#: boring: this is a router, not a classifier, and it must stay predictable.
_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("incident", ("acil", "urgent", "down", "çöktü", "coktu", "hata var", "outage", "kriz")),
    ("review", ("denetle", "audit", "review", "incele", "kontrol et", "doğrula", "dogrula")),
    ("code", ("kod", "code", "bug", "test", "refactor", "commit", "fonksiyon", "script")),
    ("research", ("araştır", "arastir", "research", "kaynak", "bul", "compare", "karşılaştır")),
    ("decide", ("karar", "decide", "seç", "sec", "onayla", "strateji", "plan")),
    ("teach", ("öğret", "ogret", "açıkla", "acikla", "nasıl yapılır", "explain", "anlat")),
)

#: task -> the ingredients that task needs, in catalogue order.
_TASK_TRAITS: dict[str, tuple[str, ...]] = {
    "chat": ("assistant", "warm"),
    "question": ("assistant", "accurate", "fast"),
    "code": ("engineer", "systems", "verify", "accurate"),
    "research": ("researcher", "curious", "skeptical", "accurate"),
    "review": ("auditor", "skeptical", "verify", "honest_failure"),
    "decide": ("executive", "strategist", "cost_aware", "mature"),
    "teach": ("teacher", "gentle", "mentor"),
    "incident": ("operator", "calm", "verify", "direct"),
}

_AUDIENCE_TRAITS: dict[str, tuple[str, ...]] = {
    "owner": ("subordinate", "direct"),
    "peer": ("peer",),
    "agent": ("direct", "verify"),
    "external": ("negotiator", "gentle"),
}

#: task -> the skill pack whose hands that task needs.
_TASK_PACKS: dict[str, str] = {
    "chat": "assistant",
    "question": "assistant",
    "code": "engineer",
    "research": "researcher",
    "review": "auditor",
    "decide": "executive",
    "teach": "teacher",
    "incident": "operator",
}


@dataclass(frozen=True, slots=True)
class Situation:
    """What the moment is: deterministic, readonly, explainable."""

    task: str = "chat"
    audience: str = "owner"
    urgency: str = "normal"
    reversibility: str = "reversible"
    channel: str = "text"
    language: str = "de"
    cues: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "audience": self.audience,
            "urgency": self.urgency,
            "reversibility": self.reversibility,
            "channel": self.channel,
            "language": self.language,
            "cues": list(self.cues),
        }


@dataclass(frozen=True, slots=True)
class Selection:
    """The chosen ingredients AND why - the part that can be argued with."""

    ingredients: tuple[str, ...]
    reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)
    situation: Situation = field(default_factory=Situation)

    def explain(self) -> str:
        lines = [
            "selection: "
            + f"task={self.situation.task} audience={self.situation.audience} "
            + f"urgency={self.situation.urgency} reversibility={self.situation.reversibility} "
            + f"channel={self.situation.channel} language={self.situation.language}"
        ]
        for trait_id in self.ingredients:
            why = ", ".join(self.reasons.get(trait_id, ()))
            lines.append(f"  - {trait_id}: {why}")
        return "\n".join(lines)


def infer_task(text: str) -> tuple[str, tuple[str, ...]]:
    """The task a piece of text points at, with the cue that decided it."""
    lowered = str(text or "").lower()
    hits: list[str] = []
    for task, cues in _CUES:
        for cue in cues:
            if cue in lowered:
                hits.append(cue)
                return task, tuple(hits)
    return "chat", ()


def analyse(
    *,
    task: str | None = None,
    audience: str | None = None,
    urgency: str | None = None,
    reversibility: str | None = None,
    channel: str | None = None,
    language: str | None = None,
    text: str = "",
) -> Situation:
    """Read the moment. Anything missing is inferred, then defaulted."""
    cues: tuple[str, ...] = ()
    if task is None:
        task, cues = infer_task(text)
    chosen_task = task if task in TASKS else "chat"
    # An incident outranks a calm reading of the same words.
    if urgency is None and chosen_task == "incident":
        urgency = "high"
    return Situation(
        task=chosen_task,
        audience=audience if audience in AUDIENCES else "owner",
        urgency=urgency if urgency in URGENCIES else "normal",
        reversibility=(
            reversibility if reversibility in ("reversible", "irreversible") else "reversible"
        ),
        channel=channel if channel in CHANNELS else "text",
        language=str(language or "de").strip().lower() or "de",
        cues=cues,
    )


def select(situation: Situation) -> Selection:
    """The ingredients for a moment, each with the reason it was chosen."""
    ordered: list[str] = []
    reasons: dict[str, list[str]] = {}

    def add(trait_id: str, why: str) -> None:
        if trait_id not in ordered:
            ordered.append(trait_id)
        reasons.setdefault(trait_id, []).append(why)

    for trait_id in _TASK_TRAITS.get(situation.task, _TASK_TRAITS["chat"]):
        add(trait_id, f"task={situation.task}")
    for trait_id in _AUDIENCE_TRAITS.get(situation.audience, ()):
        add(trait_id, f"audience={situation.audience}")

    if situation.channel == "voice":
        add("voice_short", "channel=voice")
    else:
        add("written_full", "channel=text")
    if situation.urgency == "high":
        add("fast", "urgency=high")
    else:
        add("thorough", f"urgency={situation.urgency}")
    if situation.reversibility == "irreversible":
        add("ask_first", "reversibility=irreversible")
        add("verify", "reversibility=irreversible")
    else:
        add("autonomous", "reversibility=reversible")
    if situation.language not in ("de", "en"):
        add("multilingual", f"language={situation.language}")

    # Every character carries the house limits; they are never negotiable.
    for trait_id in ("no_destroy", "no_secrets", "honest_failure"):
        add(trait_id, "always")

    return Selection(
        ingredients=tuple(ordered),
        reasons={k: tuple(v) for k, v in reasons.items()},
        situation=situation,
    )


def persona_for(
    *,
    name: str | None = None,
    **signals: Any,
) -> Any:
    """Analyse, select, and compose - the one call a caller needs."""
    from jarvis.persona.character import compose  # noqa: PLC0415 - keeps this file light

    situation = analyse(**signals)
    selection = select(situation)
    persona = compose(name or situation.task, list(selection.ingredients))
    return persona, selection


def pack_for(situation: Situation) -> str:
    """The skill pack whose hands this moment needs."""
    return _TASK_PACKS.get(situation.task, "assistant")


__all__ = [
    "AUDIENCES",
    "CHANNELS",
    "Selection",
    "Situation",
    "TASKS",
    "URGENCIES",
    "analyse",
    "infer_task",
    "pack_for",
    "persona_for",
    "select",
]
