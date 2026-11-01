"""Measured tool-calling verdicts for local models, keyed by behaviour.

``/api/show`` DECLARES capabilities; a declaration is a claim, not evidence.
Live 2026-10-16: ``deepseek-r1:8b`` declared ``tools`` and never emitted a
single tool call — it fabricated a tool RESULT instead ("According to the
weather tool … partly sunny 24°C") and took ~85 s per turn, while the control
``qwen3.5:4b`` called ``get_weather({"city": "Istanbul"})`` correctly. Only a
real request tells the two apart, so an explicit probe
(``scripts/check_local_models.py --tool-probe``) records what actually
happened and this store carries that verdict to the runtime gate (AP-21:
capability by behaviour, never by name or by claim).

The store is a small JSON file under the user data dir, written atomically and
read tolerantly: an unreadable file means "no verdict" (``None``) — never a
crash, and never a wrong yes. Every entry keeps its evidence, so a human can
audit why a model was refused tools, and an optional ``digest`` invalidates a
verdict once the model is re-pulled (the weights are not the ones measured).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PROBE_FILE_NAME = "model_tool_probe.json"
_STORE_VERSION = 1


def probe_path() -> Path:
    """``DATA_DIR/state/model_tool_probe.json`` — resolved at call time so a
    test (or a portable install) can redirect ``DATA_DIR``."""
    from jarvis.core import config as cfg_mod

    return Path(cfg_mod.DATA_DIR) / "state" / PROBE_FILE_NAME


def _key(provider: str, model: str) -> str:
    return f"{str(provider).strip()}/{str(model).strip()}"


def _read(path: Path) -> dict[str, Any]:
    """The store as a mapping, or an empty one when it is absent/unreadable."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # No probe store means no measured verdict yet.
        return {"version": _STORE_VERSION, "entries": {}}
    except OSError:
        log.debug("tool_probe_store: unreadable at %s", path, exc_info=True)
        return {"version": _STORE_VERSION, "entries": {}}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        log.warning(
            "tool_probe_store: %s is not valid JSON — treating every model as "
            "unprobed (the declaration still decides).",
            path,
        )
        return {"version": _STORE_VERSION, "entries": {}}
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        return {"version": _STORE_VERSION, "entries": {}}
    return data


def verdict_for(provider: str, model: str, *, digest: str | None = None) -> bool | None:
    """The MEASURED tool-calling verdict for one model, or ``None``.

    ``None`` means "no verdict" — either nothing was ever probed, or the
    recorded digest no longer matches the model on disk (it was re-pulled, so
    the measurement belongs to different weights). Callers then fall back to
    the model's own declaration.
    """
    if not provider or not model:
        return None
    entry = _read(probe_path())["entries"].get(_key(provider, model))
    if not isinstance(entry, dict):
        return None
    if digest:
        recorded = entry.get("digest")
        if isinstance(recorded, str) and recorded and recorded != digest:
            return None
    capable = entry.get("capable")
    return capable if isinstance(capable, bool) else None


def reason_for(provider: str, model: str) -> str | None:
    """Why the last probe reached its verdict (for logs, UI and diagnosis)."""
    entry = _read(probe_path())["entries"].get(_key(provider, model))
    if not isinstance(entry, dict):
        return None
    reason = entry.get("reason")
    return reason if isinstance(reason, str) else None


def entries() -> dict[str, dict[str, Any]]:
    """Every recorded verdict, keyed ``"<provider>/<model>"`` (read-only view)."""
    return dict(_read(probe_path())["entries"])


def write_verdict(
    provider: str,
    model: str,
    *,
    capable: bool | None,
    reason: str,
    evidence: str = "",
    digest: str | None = None,
) -> Path | None:
    """Record one probe OUTCOME, atomically. Never raises.

    ``capable=None`` records an attempt that proved NOTHING (a timeout, an empty
    reply, a probe that could not run). It is an audit entry only —
    ``verdict_for`` never returns a non-boolean, so it cannot gate a model —
    but its reason stays visible, so "we tried and learned nothing" is not
    silently the same as "we never tried".

    Returns the store path on success, ``None`` when the write failed — a probe
    that cannot persist its finding must say so, not pretend it was saved.
    """
    if not provider or not model:
        return None
    path = probe_path()
    try:
        from datetime import UTC, datetime

        data = _read(path)
        entry: dict[str, Any] = {
            "capable": capable if isinstance(capable, bool) else None,
            "reason": str(reason),
            "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if evidence:
            entry["evidence"] = str(evidence)[:500]
        if digest:
            entry["digest"] = str(digest)
        data["entries"][_key(provider, model)] = entry
        data["version"] = _STORE_VERSION

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tool_probe_", suffix=".tmp")
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
                # Keep the original atomic-write error on cleanup.
                pass
            raise
    except Exception:  # noqa: BLE001 — a probe result must never crash a caller
        log.warning(
            "tool_probe_store: could not record the verdict for %s",
            _key(provider, model),
            exc_info=True,
        )
        return None
    log.info(
        "tool_probe_store: recorded tools=%s for %s (%s)",
        capable,
        _key(provider, model),
        reason,
    )
    return path


__all__ = [
    "PROBE_FILE_NAME",
    "entries",
    "probe_path",
    "reason_for",
    "verdict_for",
    "write_verdict",
]
