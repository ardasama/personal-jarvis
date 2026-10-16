"""Deterministic local-model capability eval (Wave B2).

Scored in code — no judge model, no network, no paid key. The scorers are pure
functions and ``run_model_eval`` is exercised through a scripted asker. Live
2026-10-16 this suite is what separates a model that really calls tools from
one that narrates ("I can check the weather for you... please hold on").
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jarvis.local_models import eval_suite


@pytest.fixture
def report_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from jarvis.core import config as core_config

    monkeypatch.setattr(core_config, "DATA_DIR", tmp_path)
    return tmp_path / "state" / eval_suite.EVAL_FILE_NAME


def _case(name: str) -> eval_suite.EvalCase:
    return next(case for case in eval_suite.CASES if case.name == name)


def test_case_names_are_unique_and_cover_the_six_dimensions() -> None:
    names = [case.name for case in eval_suite.CASES]
    assert len(names) == len(set(names)) == len(eval_suite.CASE_NAMES)
    assert len(names) >= 5
    assert all(case.prompt.strip() for case in eval_suite.CASES)


@pytest.mark.parametrize(
    ("name", "text", "expected"),
    [
        # exact_reply
        ("exact_reply", "OK", True),
        ('exact_reply', '"OK".', True),
        ("exact_reply", "OK, here you go", False),
        ("exact_reply", "okay", False),
        # arithmetic
        ("arithmetic", "391", True),
        ("arithmetic", "The answer is 391.", True),
        ("arithmetic", "392", False),
        # structured_json
        ("structured_json", '{"city": "Istanbul", "temp_c": 21}', True),
        ("structured_json", 'Sure: {"city": "Istanbul", "temp_c": 21}', True),
        ("structured_json", '{"city": "Istanbul", "temp_c": "21"}', False),
        ("structured_json", '{"city": "Ankara", "temp_c": 21}', False),
        ("structured_json", "no json at all", False),
        # three_lines
        ("three_lines", "red\ngreen\nblue", True),
        ("three_lines", "1. red\n2. green\n3. blue", False),
        ("three_lines", "- red\n- green\n- blue", False),
        ("three_lines", "red\ngreen", False),
        # context_recall
        ("context_recall", "7-FOX-TROT", True),
        ("context_recall", "The code is 7-fox-trot.", True),
        ("context_recall", "I do not know", False),
    ],
)
def test_scorers_are_exact(name: str, text: str, expected: bool) -> None:
    assert _case(name).check(text) is expected


@pytest.mark.asyncio
async def test_a_case_that_cannot_be_asked_is_unknown_never_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timeout must not mark a model down for a request nobody answered."""

    async def _ask(root: str, model: str, prompt: str) -> tuple[str, str]:
        if "17 * 23" in prompt:
            return "", "ReadTimeout"
        return "OK", ""

    monkeypatch.setattr(eval_suite, "_ask", _ask)

    results = await eval_suite.run_model_eval("http://127.0.0.1:11434", "m")

    assert set(results) == set(eval_suite.CASE_NAMES)
    assert results["arithmetic"] is None
    assert results["exact_reply"] is True
    assert results["three_lines"] is False  # "OK" is not three lines


@pytest.mark.asyncio
async def test_an_empty_reply_scores_false_not_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ask(root: str, model: str, prompt: str) -> tuple[str, str]:
        return "", ""

    monkeypatch.setattr(eval_suite, "_ask", _ask)

    results = await eval_suite.run_model_eval("http://127.0.0.1:11434", "m")

    assert all(value is False for value in results.values())


def test_the_report_merges_the_measured_tool_verdict(
    report_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "jarvis.brain.tool_probe_store.verdict_for",
        lambda provider, model, **kwargs: False,
    )

    path = eval_suite.write_report(
        "ollama", "m", cases={"exact_reply": True, "arithmetic": False}
    )

    assert path == report_file
    report = eval_suite.report_for("ollama", "m")
    assert report is not None
    assert report["score"] == "1/2"
    assert report["runtime_capable"] is False
    assert report["cases"] == {"exact_reply": True, "arithmetic": False}
    assert "ollama/m" in eval_suite.reports()


def test_a_missing_tool_verdict_leaves_the_dimension_unknown(
    report_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "jarvis.brain.tool_probe_store.verdict_for",
        lambda provider, model, **kwargs: None,
    )

    eval_suite.write_report("ollama", "m", cases={"exact_reply": True})

    report = eval_suite.report_for("ollama", "m")
    assert report is not None and report["runtime_capable"] is None


def test_unattempted_cases_do_not_count_against_the_score(report_file: Path) -> None:
    eval_suite.write_report(
        "ollama", "m", cases={"exact_reply": True, "arithmetic": None}
    )
    report = eval_suite.report_for("ollama", "m")
    assert report is not None and report["score"] == "1/1"


def test_a_corrupt_report_file_is_empty_not_a_crash(report_file: Path) -> None:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text("{not json", encoding="utf-8")

    assert eval_suite.reports() == {}
    assert eval_suite.report_for("ollama", "m") is None


def test_blank_identifiers_are_refused(report_file: Path) -> None:
    assert eval_suite.write_report("", "m", cases={}) is None
    assert eval_suite.report_for("ollama", "") is None


def test_the_text_extractor_is_tolerant() -> None:
    cases: list[Any] = [None, {}, {"message": None}, {"message": {"content": None}}]
    assert all(eval_suite._text_of(payload) == "" for payload in cases)
    assert eval_suite._text_of({"message": {"content": "hi"}}) == "hi"
