"""Skill packs: a ROLE selects a bundle of the skills that already exist.

Jarvis's skill registry already carries everything a skill needs to be judged
(category, tags, triggers, required tools, risk policy, token budget). What it
did not have is the role layer: "the auditor needs THESE skills, and if one is
missing we say so" was implicit knowledge scattered in prompts.

A pack is data, not machinery: it names skills, states the risk posture the
role may not go below, and resolves through the REAL registry, so a pack reports
what is present, what is a draft, and what is not installed at all - never a
confident list of things that do not exist.

The bridge to character: a persona's competence traits map onto a pack, so
"compose a skeptical senior engineer" also decides which hands that character
reaches for.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SkillPack:
    """A role's hands: which skills, how risky, and what they need installed."""

    id: str
    role: str
    summary: str
    skills: tuple[str, ...] = ()
    requires_tools: tuple[str, ...] = ()
    #: The weakest risk tier this role may operate at. A pack never
    #: DOWNGRADES the product's own risk policy; it only records the floor.
    risk_floor: str = "monitor"


PACKS: dict[str, SkillPack] = {
    "assistant": SkillPack(
        "assistant", "Personal assistant",
        "Everyday hands: the product's own tools, no specialist skills.",
        skills=(),
    ),
    "engineer": SkillPack(
        "engineer", "Engineer",
        "Change code, prove it, and keep the evidence.",
        skills=("test-runner", "code-reviewer", "jarvis-critic-design-reviewer"),
        requires_tools=("run_shell", "read_file", "write_file"),
    ),
    "auditor": SkillPack(
        "auditor", "Auditor",
        "Trust the log, not the story: review, verify, and report gaps as gaps.",
        skills=(
            "code-reviewer", "plan-verifier", "docs-privacy-reviewer",
            "phase7-selfmod-auditor",
        ),
        risk_floor="ask",
    ),
    "researcher": SkillPack(
        "researcher", "Researcher",
        "Find what exists before building anything new.",
        skills=("drive-jarvis-cli",),
        requires_tools=("search_web",),
    ),
    "executive": SkillPack(
        "executive", "Executive",
        "Decide, delegate, and report: the hub's own supervision skills.",
        skills=("plan-verifier",),
        risk_floor="ask",
    ),
    "operator": SkillPack(
        "operator", "Operator",
        "Get it done in order, today, with the platform's own hands.",
        skills=("generate-cli-command", "drive-jarvis-cli"),
        requires_tools=("run_shell",),
    ),
    "teacher": SkillPack(
        "teacher", "Teacher",
        "Leave the person able to do it alone next time.",
        skills=("drive-jarvis-cli",),
    ),
}

#: Which persona competence turns a character into a role's hands.
_COMPETENCE_TO_PACK: dict[str, str] = {
    "engineer": "engineer",
    "auditor": "auditor",
    "researcher": "researcher",
    "executive": "executive",
    "strategist": "executive",
    "operator": "operator",
    "teacher": "teacher",
    "mentor": "teacher",
}


def pack(pack_id: str) -> SkillPack | None:
    """The pack for ``pack_id``, or ``None`` when there is no such role."""
    return PACKS.get(str(pack_id or "").strip())


def pack_for_persona(persona: Any) -> SkillPack:
    """The hands a composed character reaches for.

    A persona carries competence ingredients (engineer, auditor, teacher...);
    the LAST one wins, exactly as it decides the specialty. An unknown or empty
    character falls back to the everyday assistant, never to a specialist.
    """
    ingredients = list(getattr(persona, "ingredients", ()) or ())
    for trait_id in reversed(ingredients):
        pack_id = _COMPETENCE_TO_PACK.get(str(trait_id))
        if pack_id is not None:
            return PACKS[pack_id]
    return PACKS["assistant"]


def resolve_pack(pack_id: str, registry: Any) -> dict[str, Any]:
    """What a pack means against the REAL registry. Never claims what is absent.

    ``registry`` needs ``get(name)`` -> object with ``state`` (or ``None``).
    A missing registry is reported, not guessed: the pack still lists what it
    WOULD need, and ``resolved`` is ``False``.
    """
    selected = pack(pack_id)
    if selected is None:
        return {"pack": pack_id, "resolved": False, "reason": "unknown pack"}
    present: list[str] = []
    drafts: list[str] = []
    missing: list[str] = []
    for name in selected.skills:
        entry = None
        try:
            entry = registry.get(name) if registry is not None else None
        except Exception:  # noqa: BLE001 - an unreadable registry is "unknown"
            log.debug("skillpack: registry lookup failed for %s", name, exc_info=True)
            entry = None
        if entry is None:
            missing.append(name)
            continue
        state = str(getattr(entry, "state", "") or "").lower()
        if state in ("draft", "validated"):
            drafts.append(name)
        else:
            present.append(name)
    return {
        "pack": selected.id,
        "role": selected.role,
        "summary": selected.summary,
        "risk_floor": selected.risk_floor,
        "requires_tools": list(selected.requires_tools),
        "present": present,
        "drafts": drafts,
        "missing": missing,
        # A pack is only "resolved" when nothing it names is missing: a role
        # without its hands is a promise, not a capability.
        "resolved": not missing,
    }


__all__ = ["PACKS", "SkillPack", "pack", "pack_for_persona", "resolve_pack"]
