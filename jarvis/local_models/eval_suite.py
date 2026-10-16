"""Deterministic local-model capability eval, scored in code (no judge model).

Wave B of the local-model reliability work answers one question with evidence
instead of vibes: WHICH downloaded model is good enough to be a runtime brain?
The tool dimension is already measured by ``--tool-probe`` (and carried in
``tool_probe_store``); this suite adds the other five dimensions every local
brain is asked for, each with a scorer that cannot be fooled by a confident
tone:

1. ``exact_reply``     — follow an exact-output instruction.
2. ``arithmetic``      — get one small multiplication right.
3. ``structured_json`` — emit the requested JSON shape.
4. ``three_lines``     — obey a cheap formatting constraint.
5. ``context_recall``  — find a needle in the prompt it was just given.

Scoring is pure Python: a case either did what it was told or it did not, so a
report is reproducible and costs one request per case. Nothing here pays an
API key — it runs against a local server and unloads the model afterwards.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

EVAL_FILE_NAME = "model_eval.json"
_STORE_VERSION = 1


@dataclass(frozen=True)
class EvalCase:
    """One prompt with a scorer that decides pass/fail in code."""

    name: str
    prompt: str
    check: Callable[[str], bool]


def _text_of(payload: Any) -> str:
    """The assistant text of one native ``/api/chat`` payload ("" when absent)."""
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


def _exact_ok(text: str) -> bool:
    return text.strip().strip("\"'.").upper() == "OK"


def _arithmetic_ok(text: str) -> bool:
    return "391" in text.replace(",", "").replace(" ", "")


def _json_ok(text: str) -> bool:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return False
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    if str(data.get("city", "")).strip().lower() != "istanbul":
        return False
    temperature = data.get("temp_c")
    return isinstance(temperature, int) and not isinstance(temperature, bool)


def _three_lines_ok(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 3:
        return False
    # "1. red" / "- red" / "* red" are constraints the prompt forbade.
    return not any(line[:1].isdigit() or line[:1] in "-*" for line in lines)


_RECALL_CODE = "7-FOX-TROT"

CASES: tuple[EvalCase, ...] = (
    EvalCase(
        name="exact_reply",
        prompt="Reply with exactly this word and nothing else: OK",
        check=_exact_ok,
    ),
    EvalCase(
        name="arithmetic",
        prompt="What is 17 * 23? Reply with the number only.",
        check=_arithmetic_ok,
    ),
    EvalCase(
        name="structured_json",
        prompt=(
            'Return ONLY this JSON and nothing else: '
            '{"city": "Istanbul", "temp_c": 21}'
        ),
        check=_json_ok,
    ),
    EvalCase(
        name="three_lines",
        prompt=(
            "List exactly three colors, one per line, without bullets or "
            "numbering."
        ),
        check=_three_lines_ok,
    ),
    EvalCase(
        name="context_recall",
        prompt=(
            "The maintenance log says: the boiler was serviced in March and "
            f"the access code is {_RECALL_CODE}. Which access code does the "
            "log name? Reply with the code only."
        ),
        check=lambda text: _RECALL_CODE in text.upper(),
    ),
)

CASE_NAMES: tuple[str, ...] = tuple(case.name for case in CASES)


def report_path() -> Path:
    """``DATA_DIR/state/model_eval.json`` — resolved at call time."""
    from jarvis.core import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / "state" / EVAL_FILE_NAME


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"version": _STORE_VERSION, "models": {}}
    except OSError:
        log.debug("eval_suite: unreadable at %s", path, exc_info=True)
        return {"version": _STORE_VERSION, "models": {}}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        log.warning("eval_suite: %s is not valid JSON — treating it as empty.", path)
        return {"version": _STORE_VERSION, "models": {}}
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        return {"version": _STORE_VERSION, "models": {}}
    return data


def reports() -> dict[str, dict[str, Any]]:
    """Every recorded report, keyed ``"<provider>/<model>"``."""
    return dict(_read(report_path())["models"])


def report_for(provider: str, model: str) -> dict[str, Any] | None:
    """The last report for one model, or ``None``."""
    entry = _read(report_path())["models"].get(f"{provider}/{model}")
    return dict(entry) if isinstance(entry, dict) else None


def write_report(
    provider: str,
    model: str,
    *,
    cases: dict[str, bool | None],
    digest: str | None = None,
) -> Path | None:
    """Persist one model's case results atomically. Never raises."""
    if not provider or not model:
        return None
    path = report_path()
    try:
        from datetime import UTC, datetime

        data = _read(path)
        runtime = _read_runtime_capability(provider, model)
        passed = sum(1 for value in cases.values() if value is True)
        attempted = sum(1 for value in cases.values() if value is not None)
        data["models"][f"{provider}/{model}"] = {
            "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "cases": dict(cases),
            "score": f"{passed}/{attempted}" if attempted else "0/0",
            "runtime_capable": runtime,
            "digest": digest,
        }
        data["version"] = _STORE_VERSION

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".model_eval_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:  # noqa: BLE001 — a report must never crash the caller
        log.warning(
            "eval_suite: could not record the report for %s/%s", provider, model, exc_info=True
        )
        return None
    log.info(
        "eval_suite: recorded %s for %s/%s",
        data["models"][f"{provider}/{model}"]["score"],
        provider,
        model,
    )
    return path


def _read_runtime_capability(provider: str, model: str) -> bool | None:
    """Fold in the tool-calling verdict the probe already measured.

    The sixth dimension lives in ``tool_probe_store`` (it costs a real request
    with a fake tool), so the eval report reads it instead of asking again.
    """
    try:
        from jarvis.brain.tool_probe_store import verdict_for

        return verdict_for(provider, model)
    except Exception:  # noqa: BLE001 — a missing verdict is simply unknown
        log.debug("eval_suite: tool verdict lookup failed", exc_info=True)
        return None


async def _ask(root: str, model: str, prompt: str) -> tuple[str, str]:
    """One native ``/api/chat`` turn. Returns ``(text, error)``."""
    import httpx

    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": 0,
        "options": {"temperature": 0},
    }
    try:
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{root}/api/chat", json=body)
            response.raise_for_status()
            return _text_of(response.json()), ""
    except Exception as exc:  # noqa: BLE001 — an unreachable server is a result
        return "", str(exc)[:200]


async def run_model_eval(root: str, model: str) -> dict[str, bool | None]:
    """Score every case for one model. ``None`` = the case could not be run.

    A case that could not be asked (a timeout, a dead server) is recorded as
    ``None`` — never as a failure: a model must not be marked down for a
    request the server never answered.
    """
    results: dict[str, bool | None] = {}
    for case in CASES:
        text, error = await _ask(root, model, case.prompt)
        if error:
            log.warning("eval_suite: %s case %r failed to run: %s", model, case.name, error)
            results[case.name] = None
            continue
        results[case.name] = bool(case.check(text))
    return results


__all__ = [
    "CASES",
    "CASE_NAMES",
    "EVAL_FILE_NAME",
    "EvalCase",
    "report_for",
    "report_path",
    "reports",
    "run_model_eval",
    "write_report",
]
