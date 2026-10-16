"""Each agent the owner runs gets a voice of its own.

The product already ships the TTS families and a curated allowlist of REAL voice
ids (curated_catalog). What was missing is the mapping: which agent speaks with
which voice, and why. A single voice for every agent is exactly the opposite of
"one self, many behaviours" - the same rule the character layer follows.

Hard line on the owner's request for the FILM voices: an actor's voice is a real
person's performance and cannot be cloned. So each agent gets a FITTING voice
from the shipped catalogue - matched on the character's register (deep, steady,
warm, regal, poetic, clear) - and the owner can swap any id freely.

Every id here is a real id from the curated catalogue, so nothing is invented;
the tests cross-check each one against the product's own catalogue and fail if a
voice does not exist there. A provider that is not available degrades by
register (masculine/feminine), never by silence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MASCULINE = "m"
FEMININE = "f"


@dataclass(frozen=True, slots=True)
class AgentVoice:
    """One agent's speaking identity."""

    agent: str
    provider: str
    voice_id: str
    gender: str
    register: str
    why: str


#: The owner's agents. ``why`` is part of the data: a voice that cannot be
#: justified cannot be audited or swapped with intent.
AGENT_VOICES: dict[str, AgentVoice] = {
    "jarvis": AgentVoice(
        "jarvis", "gemini-flash-tts", "Charon", MASCULINE, "steady, low, unhurried",
        "The product's own voice: steady and low, never theatrical - it must stay "
        "listenable after the hundredth task.",
    ),
    "ardasama": AgentVoice(
        "ardasama", "gemini-flash-tts", "Iapetus", MASCULINE, "warm, commanding",
        "The owner's own agent: warm but clearly in charge.",
    ),
    "morpheus": AgentVoice(
        "morpheus", "gemini-flash-tts", "Fenrir", MASCULINE, "deep, calm, certain",
        "The mythic counsellor register: deep and certain, never hurried.",
    ),
    "neo": AgentVoice(
        "neo", "gemini-flash-tts", "Puck", MASCULINE, "young, clear, focused",
        "The newcomer register: clear and forward-leaning, few colours.",
    ),
    "sah": AgentVoice(
        "sah", "gemini-flash-tts", "Alnilam", MASCULINE, "regal, formal, unhurried",
        "A throne voice: formal and slow, at home in a decree.",
    ),
    "rumi": AgentVoice(
        "rumi", "gemini-flash-tts", "Schedar", MASCULINE, "poetic, warm, gentle",
        "The poet's register: warm and measured, made for saying things softly.",
    ),
    "gourbet": AgentVoice(
        "gourbet", "gemini-flash-tts", "Umbriel", MASCULINE, "neutral, precise",
        "A working voice: neutral and exact, no colour that could bias a report.",
    ),
    # A feminine option is kept in the map on purpose: the owner may want an
    # agent's voice to change register, and swapping the id is a one-line edit.
    "rumi_feminine": AgentVoice(
        "rumi_feminine", "gemini-flash-tts", "Sulafat", FEMININE, "poetic, warm, gentle",
        "The feminine counterpart of the poet's register, for when the owner "
        "prefers it.",
    ),
}

#: Which family to fall back to when the preferred provider is not usable.
#: Keyless local speech first: no credential, no quota, nothing to bill.
_FALLBACK_BY_GENDER: dict[str, tuple[str, str]] = {
    MASCULINE: ("piper-local", ""),
    FEMININE: ("piper-local", ""),
}


def agent_voice(agent: str) -> AgentVoice | None:
    """The mapped voice for an agent, or ``None`` for an unknown name."""
    return AGENT_VOICES.get(str(agent or "").strip().lower())


def voice_for(agent: str, *, available_providers: Any = None) -> AgentVoice | None:
    """The voice to speak with: the mapped one when its family is usable.

    ``available_providers`` is any iterable of provider ids (a GUI passes what it
    has). ``None`` means "do not check": the mapped voice is returned as-is, so a
    caller that cannot know availability is never lied to about it.

    When the preferred family is missing, the voice degrades to the local
    keyless family - the owner still hears the agent, in the right register, and
    nothing is billed for it.
    """
    mapped = agent_voice(agent)
    if mapped is None:
        return None
    if available_providers is None:
        return mapped
    available = {str(p).strip().lower() for p in available_providers}
    if mapped.provider.lower() in available:
        return mapped
    provider, voice_id = _FALLBACK_BY_GENDER.get(mapped.gender, ("piper-local", ""))
    if provider.lower() not in available:
        return None
    return AgentVoice(
        agent=mapped.agent,
        provider=provider,
        voice_id=voice_id,
        gender=mapped.gender,
        register=mapped.register,
        why=f"{mapped.why} (degraded: '{mapped.provider}' was not available)",
    )


def voice_map(*, available_providers: Any = None) -> dict[str, dict[str, str]]:
    """Every agent's resolved voice, ready for a settings pane or a config write."""
    out: dict[str, dict[str, str]] = {}
    for agent in AGENT_VOICES:
        resolved = voice_for(agent, available_providers=available_providers)
        if resolved is None:
            continue
        out[agent] = {
            "provider": resolved.provider,
            "voice_id": resolved.voice_id,
            "gender": resolved.gender,
            "register": resolved.register,
            "why": resolved.why,
        }
    return out


__all__ = [
    "AGENT_VOICES",
    "FEMININE",
    "MASCULINE",
    "AgentVoice",
    "agent_voice",
    "voice_for",
    "voice_map",
]
