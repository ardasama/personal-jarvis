"""Situation and selection: deterministic, explainable, verified offline."""
from __future__ import annotations

import pytest

from jarvis.persona.character import TRAITS
from jarvis.persona.situation import analyse, infer_task, pack_for, persona_for, select


def test_the_text_alone_is_enough_to_read_the_task() -> None:
    assert infer_task("acil, sistem çöktü")[0] == "incident"
    assert infer_task("bu kodu refactor et")[0] == "code"
    assert infer_task("kaynakları araştır")[0] == "research"
    assert infer_task("bunu nasıl yapılır anlat")[0] == "teach"
    assert infer_task("merhaba")[0] == "chat"


def test_an_incident_raises_its_own_urgency() -> None:
    assert analyse(text="acil durum").urgency == "high"
    assert analyse(text="merhaba").urgency == "normal"


def test_an_unknown_signal_never_becomes_a_specialist() -> None:
    situation = analyse(task="wizardry", audience="goblin", channel="smoke")
    selection = select(situation)

    assert situation.task == "chat" and situation.audience == "owner"
    assert situation.channel == "text"
    assert "assistant" in selection.ingredients


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("code", "engineer"),
        ("review", "auditor"),
        ("research", "researcher"),
        ("decide", "executive"),
        ("teach", "teacher"),
        ("incident", "operator"),
        ("chat", "assistant"),
    ],
)
def test_each_task_reaches_for_its_own_craft(task: str, expected: str) -> None:
    assert expected in select(analyse(task=task)).ingredients


def test_channel_decides_the_length_rule() -> None:
    assert "voice_short" in select(analyse(task="chat", channel="voice")).ingredients
    assert "written_full" in select(analyse(task="chat", channel="text")).ingredients


def test_the_irreversible_moment_asks_before_it_acts() -> None:
    risky = select(analyse(task="code", reversibility="irreversible")).ingredients
    calm = select(analyse(task="code", reversibility="reversible")).ingredients

    assert "ask_first" in risky and "verify" in risky
    assert "autonomous" in calm


def test_the_audience_changes_only_the_manner() -> None:
    owner = select(analyse(task="question", audience="owner")).ingredients
    external = select(analyse(task="question", audience="external")).ingredients

    assert "assistant" in owner and "assistant" in external  # same craft
    assert "subordinate" in owner and "negotiator" in external  # different manner


def test_a_third_language_is_answered_multilingually() -> None:
    assert "multilingual" in select(analyse(task="chat", language="tr")).ingredients
    assert "multilingual" not in select(analyse(task="chat", language="de")).ingredients


def test_the_house_limits_are_in_every_character() -> None:
    for task in ("chat", "code", "review", "incident", "teach"):
        ingredients = select(analyse(task=task)).ingredients
        assert {"no_destroy", "no_secrets", "honest_failure"} <= set(ingredients)


def test_every_selected_ingredient_exists_and_is_explained() -> None:
    selection = select(analyse(task="review", audience="agent", urgency="high"))

    unknown = [i for i in selection.ingredients if i not in TRAITS]
    assert not unknown
    for trait_id in selection.ingredients:
        assert selection.reasons.get(trait_id), f"{trait_id} has no reason"
    assert "review" in selection.explain()


def test_the_same_moment_always_gives_the_same_character() -> None:
    first = persona_for(text="acil, sunucu çöktü", audience="agent", channel="voice")
    second = persona_for(text="acil, sunucu çöktü", audience="agent", channel="voice")

    assert first[0].ingredients == second[0].ingredients
    assert first[0].describe() == second[0].describe()


def test_no_limits_are_lost_when_the_urgency_climbs() -> None:
    calm = persona_for(task="code", urgency="low")[0]
    hot = persona_for(task="incident", urgency="high")[0]

    assert set(calm.forbids) <= set(hot.forbids)


def test_the_pack_follows_the_task() -> None:
    assert pack_for(analyse(task="review")) == "auditor"
    assert pack_for(analyse(task="incident")) == "operator"
    assert pack_for(analyse(task="chat")) == "assistant"


def test_a_composed_character_is_usable_in_both_lengths() -> None:
    persona, selection = persona_for(task="teach", channel="voice")

    assert persona.describe()
    assert persona.describe(short=True).startswith(f"As {persona.name}:")
    assert selection.explain()
