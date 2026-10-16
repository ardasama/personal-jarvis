"""Semantic long-term memory, verified offline.

The embedder is the ONE external dependency, so it is faked: the tests never
reach a network. They pin what matters - a memory survives a restart, the
closest meaning ranks first, and an unreachable embedder says so instead of
storing a half-made memory.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.memory import semantic


@pytest.fixture
def index(tmp_path: Path) -> semantic.SemanticIndex:
    return semantic.SemanticIndex(tmp_path / "semantic_memory.db")


def _fake_embedder(monkeypatch: pytest.MonkeyPatch, vectors: dict[str, list[float]]) -> None:
    """Replace the single HTTP seam: text in, vector out."""

    async def _post(url: str, payload: dict[str, object]) -> dict[str, object] | None:
        vector = vectors.get(str(payload.get("prompt") or ""))
        return {"embedding": vector} if vector is not None else None

    monkeypatch.setattr(semantic, "_post_json", _post)


# ------------------------------------------------------------------ vectors


def test_cosine_reads_similarity_both_ways() -> None:
    assert semantic.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert semantic.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert semantic.cosine([1.0, 1.0], [1.0, 1.0]) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("a", "b"),
    [([], [1.0]), ([1.0], []), ([0.0, 0.0], [1.0, 1.0]), ([1.0], [1.0, 2.0])],
)
def test_cosine_never_raises_on_unusable_input(a: list[float], b: list[float]) -> None:
    assert semantic.cosine(a, b) == 0.0


def test_a_vector_that_is_not_one_is_refused() -> None:
    assert semantic._vector_of(None) is None
    assert semantic._vector_of({}) is None
    assert semantic._vector_of({"embedding": []}) is None
    assert semantic._vector_of({"embedding": "nope"}) is None
    assert semantic._vector_of({"embedding": [1, 2]}) == [1.0, 2.0]


# ------------------------------------------------------------------ storage


def test_a_memory_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "semantic_memory.db"
    first = semantic.SemanticIndex(path)
    assert first.add("the boiler was serviced in March", [1.0, 0.0], kind="note") is not None
    assert first.count() == 1

    reopened = semantic.SemanticIndex(path)  # a new process would do this

    assert reopened.count() == 1
    hits = reopened.search([1.0, 0.0], limit=1)
    assert hits and hits[0]["text"] == "the boiler was serviced in March"


def test_the_closest_meaning_ranks_first(index: semantic.SemanticIndex) -> None:
    index.add("the boiler was serviced in March", [1.0, 0.0], kind="note")
    index.add("the cat is asleep on the keyboard", [0.0, 1.0], kind="note")

    hits = index.search([0.9, 0.1], limit=2)

    assert [hit["text"] for hit in hits] == [
        "the boiler was serviced in March",
        "the cat is asleep on the keyboard",
    ]
    assert hits[0]["score"] > hits[1]["score"]


def test_kind_narrows_the_search(index: semantic.SemanticIndex) -> None:
    index.add("a preference", [1.0, 0.0], kind="profile")
    index.add("an episode", [1.0, 0.0], kind="note")

    hits = index.search([1.0, 0.0], limit=5, kind="profile")

    assert [hit["kind"] for hit in hits] == ["profile"]
    assert index.count(kind="note") == 1


@pytest.mark.parametrize(("text", "vector"), [("", [1.0]), ("  ", [1.0]), ("ok", [])])
def test_an_empty_memory_is_refused(
    index: semantic.SemanticIndex, text: str, vector: list[float]
) -> None:
    assert index.add(text, vector) is None
    assert index.count() == 0


def test_a_useless_query_returns_nothing(index: semantic.SemanticIndex) -> None:
    index.add("a memory", [1.0, 0.0])
    assert index.search([], limit=5) == []
    assert index.search([1.0, 0.0], limit=0) == []


def test_a_row_with_an_unreadable_vector_is_skipped_not_fatal(
    index: semantic.SemanticIndex,
) -> None:
    index.add("good", [1.0, 0.0])
    with index._connect() as connection:
        connection.execute(
            "INSERT INTO semantic_memory (kind, ref, text, vector, dim, created_at)"
            " VALUES ('note', '', 'broken', '{not json', 1, 'now')"
        )

    hits = index.search([1.0, 0.0], limit=5)

    assert [hit["text"] for hit in hits] == ["good"]


# ------------------------------------------------------------- the two verbs


@pytest.mark.asyncio
async def test_remember_and_recall_round_trip(
    index: semantic.SemanticIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_embedder(
        monkeypatch,
        {
            "the access code is 7-FOX-TROT": [1.0, 0.0],
            "what is the access code": [1.0, 0.0],
        },
    )

    assert await semantic.remember("the access code is 7-FOX-TROT", index=index) is True
    hits = await semantic.recall("what is the access code", index=index)

    assert hits and "7-FOX-TROT" in hits[0]["text"]


@pytest.mark.asyncio
async def test_an_unreachable_embedder_stores_nothing(
    index: semantic.SemanticIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail honestly: no half-made memory, and no invented answer."""
    _fake_embedder(monkeypatch, {})

    assert await semantic.remember("something", index=index) is False
    assert await semantic.recall("something", index=index) == []
    assert index.count() == 0


@pytest.mark.asyncio
async def test_a_blank_text_is_never_embedded(index: semantic.SemanticIndex) -> None:
    assert await semantic.embed("   ") is None
