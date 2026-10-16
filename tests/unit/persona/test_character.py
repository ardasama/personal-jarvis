"""Character: traits compose into a persona, verified offline.

No I/O and no product imports - the module is deliberately portable, so these
tests are too. They pin the properties a composed character must keep: limits
never shrink, a conflict is reported instead of hidden, and the LAST ingredient
decides the specialty.
"""
from __future__ import annotations

import pytest

from jarvis.persona.character import AXES, RECIPES, TRAITS, compose, recipe

# The user's own example: a working engineer who teaches.
_COMPOUND = [
    "engineer", "researcher", "skeptical", "playful", "mature", "progressive", "teacher",
]


# ------------------------------------------------------------- the catalogue


def test_every_trait_is_self_consistent() -> None:
    for key, trait in TRAITS.items():
        assert trait.id == key
        assert trait.axis in AXES
        assert trait.label.strip() and trait.summary.strip()
        assert trait.effects, f"{key} has no behaviour"
        assert len(set(trait.effects)) == len(trait.effects)
        for rival in trait.conflicts:
            assert rival in TRAITS, f"{key} conflicts with an unknown trait {rival}"
            assert TRAITS[rival].axis == trait.axis, f"{key}/{rival} cross axes"
            assert key in TRAITS[rival].conflicts, f"{key} -> {rival} is not mutual"
        for wanted in trait.wants:
            assert wanted in TRAITS, f"{key} wants an unknown trait {wanted}"


def test_every_recipe_uses_ingredients_that_exist() -> None:
    for name, ids in RECIPES.items():
        assert ids, f"recipe {name} is empty"
        assert not [i for i in ids if i not in TRAITS], f"recipe {name} has a phantom"


def test_at_least_one_trait_per_axis_so_a_character_can_be_built() -> None:
    covered = {trait.axis for trait in TRAITS.values()}
    assert covered == set(AXES)


# -------------------------------------------------------------- composing


def test_the_compound_example_composes_without_unknowns() -> None:
    persona = compose("engineer-who-teaches", _COMPOUND)
    assert persona.unknown == ()
    assert set(_COMPOUND) <= set(persona.ingredients)
    assert "teacher" in persona.ingredients


def test_the_last_ingredient_decides_the_specialty() -> None:
    """Drop 'teacher' and the same person stops teaching."""
    with_teacher = compose("x", [*_COMPOUND, "teacher"])
    without = compose("x", _COMPOUND[:-1])
    teaching = TRAITS["teacher"].effects[0]

    assert teaching in with_teacher.describe()
    assert teaching not in without.describe()


def test_an_unknown_ingredient_is_reported_and_ignored() -> None:
    persona = compose("x", ["engineer", "astronaut", "wizard"])
    assert set(persona.unknown) == {"astronaut", "wizard"}
    assert persona.describe()  # still a usable character
    assert "wizard" in persona.describe()


def test_limits_only_ever_grow() -> None:
    """Adding an ingredient may never unlock what restraint had closed."""
    base = compose("x", ["engineer"])
    more = compose("x", ["engineer", "auditor", "senior_engineer"])
    assert set(base.forbids) <= set(more.forbids)


def test_a_conflict_is_resolved_by_order_and_reported() -> None:
    fast_first = compose("x", ["fast", "thorough"])
    thorough_first = compose("x", ["thorough", "fast"])

    assert fast_first.conflicts or thorough_first.conflicts
    assert fast_first.describe() != thorough_first.describe()
    kept = fast_first.effects["cognition"]
    assert TRAITS["thorough"].effects[0] in kept  # the later ingredient wins
    assert "Tensions resolved" in fast_first.describe()


def test_no_conflict_is_invented_when_the_traits_agree() -> None:
    persona = compose("x", ["engineer", "verify", "accurate"])
    assert persona.conflicts == ()


# --------------------------------------------------------------- describing


def test_both_lengths_come_from_one_recipe() -> None:
    persona = compose("x", _COMPOUND)
    long_form = persona.describe()
    short_form = persona.describe(short=True)

    assert len(short_form) < len(long_form) / 3
    assert "\n" not in short_form
    assert persona.describe(short=True) == short_form  # deterministic


def test_the_full_form_names_the_axes_and_the_never_list() -> None:
    persona = compose("x", ["engineer", "no_destroy", "honest_failure"])
    text = persona.describe()

    assert "## Character:" in text
    assert "### Never" in text
    assert "delete user data" in text
    assert "claim unverified success" in text


# ------------------------------------------------------------------ recipes


@pytest.mark.parametrize("name", sorted(RECIPES))
def test_every_printed_recipe_builds_a_real_character(name: str) -> None:
    persona = recipe(name)
    assert persona.name == name
    assert persona.unknown == ()
    assert persona.effects
    assert persona.describe(short=True).startswith(f"As {name}:")


def test_an_unknown_recipe_is_an_empty_character_not_a_crash() -> None:
    persona = recipe("does-not-exist")
    assert persona.ingredients == ()
    assert persona.describe()
