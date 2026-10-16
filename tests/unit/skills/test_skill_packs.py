"""Skill packs: a role selects existing skills, verified offline.

The registry is faked: these tests pin what a pack must never do - claim a
skill it cannot see, downgrade a risk floor, or hand a specialist's role to an
unknown character.
"""
from __future__ import annotations

from jarvis.persona.character import compose
from jarvis.skills.packs import PACKS, pack, pack_for_persona, resolve_pack

_TIERS = {"safe", "monitor", "ask", "block"}


class _Entry:
    def __init__(self, state: str) -> None:
        self.state = state


class _Registry:
    def __init__(self, states: dict[str, str]) -> None:
        self._states = states

    def get(self, name: str):
        state = self._states.get(name)
        return _Entry(state) if state is not None else None


def test_every_pack_is_well_formed() -> None:
    for key, item in PACKS.items():
        assert item.id == key
        assert item.role.strip() and item.summary.strip()
        assert item.risk_floor in _TIERS
        for name in (*item.skills, *item.requires_tools):
            assert isinstance(name, str) and name.strip()


def test_an_unknown_pack_is_none_not_an_error() -> None:
    assert pack("nope") is None
    assert pack("") is None


def test_a_character_reaches_for_the_last_competence() -> None:
    engineer = compose("e", ["engineer", "skeptical", "thorough"])
    teacher = compose("t", ["engineer", "teacher"])

    assert pack_for_persona(engineer).id == "engineer"
    assert pack_for_persona(teacher).id == "teacher"  # the last ingredient wins


def test_an_unknown_character_gets_the_everyday_hands() -> None:
    assert pack_for_persona(object()).id == "assistant"
    assert pack_for_persona(compose("x", ["wizard"])).id == "assistant"


def test_resolution_reports_present_drafts_and_missing() -> None:
    registry = _Registry({"plan-verifier": "active", "code-reviewer": "draft"})

    result = resolve_pack("auditor", registry)

    assert result["pack"] == "auditor"
    assert "plan-verifier" in result["present"]
    assert result["drafts"] == ["code-reviewer"]
    assert result["missing"] == ["docs-privacy-reviewer", "phase7-selfmod-auditor"]
    assert result["resolved"] is False  # a role without its hands is a promise


def test_a_missing_registry_never_becomes_a_claim() -> None:
    result = resolve_pack("engineer", None)

    assert result["resolved"] is False
    assert result["present"] == []
    assert set(result["missing"]) == set(PACKS["engineer"].skills)


def test_resolved_only_when_nothing_is_missing() -> None:
    everything = {name: "active" for name in PACKS["engineer"].skills}
    assert resolve_pack("engineer", _Registry(everything))["resolved"] is True


def test_an_unknown_pack_resolves_with_a_reason() -> None:
    result = resolve_pack("ghost", _Registry({}))
    assert result["resolved"] is False
    assert "unknown pack" in result["reason"]


# ------------------------------------------------- the bridge back: role -> self


def test_the_bridge_is_two_way() -> None:
    from jarvis.skills.packs import character_for_pack, missing_traits  # noqa: PLC0415

    persona = character_for_pack("auditor", base=("mature", "calm"))

    assert persona.name == "auditor"
    assert "mature" in persona.ingredients and "calm" in persona.ingredients
    assert missing_traits("auditor", persona) == []  # the role has its character
    assert persona.describe().strip()


def test_a_mismatched_character_reports_what_the_role_needs() -> None:
    from jarvis.skills.packs import character_for_pack, missing_traits, pack_traits  # noqa: PLC0415

    teacher = character_for_pack("teacher")
    missing = missing_traits("engineer", teacher)

    assert missing == [t for t in pack_traits("engineer") if t not in teacher.ingredients]
    assert "engineer" in missing


def test_an_unknown_role_falls_back_to_the_everyday_character() -> None:
    from jarvis.skills.packs import character_for_pack, pack_traits  # noqa: PLC0415

    assert pack_traits("nope") == pack_traits("assistant")
    assert character_for_pack("nope").name == "nope"
    assert "assistant" in character_for_pack("nope").ingredients


def test_the_pack_traits_are_real_ingredients_of_the_catalogue() -> None:
    from jarvis.persona.character import TRAITS  # noqa: PLC0415
    from jarvis.skills.packs import PACK_TRAITS  # noqa: PLC0415

    for pack_id, traits in PACK_TRAITS.items():
        assert traits, f"{pack_id} declares no character"
        unknown = [t for t in traits if t not in TRAITS]
        assert not unknown, f"{pack_id} needs traits that do not exist: {unknown}"
