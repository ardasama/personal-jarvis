#!/usr/bin/env python
"""Read-only preflight for the Local models section, runnable on any machine.

Why this exists
---------------
The Local models section has three moving parts that only ever meet on a real
user's box: the Ollama server (detected, started and pulled from), the role
picks written into ``jarvis.toml``, and the provider card that reads the SAME
config key from the other side. Every one of those legs is unit-tested with
fakes, and exactly ONE hardware profile — NVIDIA on Windows — has ever been
run live. Apple Silicon and AMD are, as of 2026-08-28, untested on metal.

This script is the drill that closes that gap without asking anyone to read
code: it runs the whole checklist against THIS machine and prints one verdict
per check, so a Mac or an AMD box can be reported with evidence instead of a
guess. It never installs and never pulls. By default it also never loads a
model into memory and never writes a file — the worst it can do is fail to
reach a server. The opt-in ``--tool-probe`` is the one exception, and it says
so: it loads ONE model at a time (``keep_alive: 0`` unloads it right after) to
measure whether it really calls tools, and records that verdict for the
runtime gate.

What it checks
--------------
1. **hardware**    — what the accelerator probe reports here, and whether that
                     answer is one the fit verdicts can actually use. A host
                     with a GPU the probe cannot read (AMD, Intel, any non-CUDA
                     card outside Apple Silicon) is the interesting case: it is
                     not an error, but every "fits / runs slowly" verdict below
                     then falls back to the system-RAM rule.
2. **runtime**     — the three-state truth (not installed / installed but
                     stopped / running), the binary path, and the models
                     directory, all per-OS.
3. **inventory**   — what the server lists, and how many of those entries are
                     Jarvis's own hidden aliases rather than real downloads.
4. **roles**       — every slot, its config key, its pick, and whether that
                     pick is actually on disk.
5. **card parity** — the check the two surfaces exist to pass: every model the
                     provider card would offer as a brain must be a model the
                     Local models section knows about. A tag on the card that
                     the section hides is a pick the user can make and then see
                     reported as "Not downloaded".
6. **autostart**   — whether this install would bring the server up on its own,
                     which is what "a new PC needs no manual step" means.
7. **tool-probe**  — opt-in (``--tool-probe``): whether each model that
                     DECLARES ``tools`` actually calls one. A declaration is a
                     claim; the runtime gate trusts a measurement. Live
                     2026-10-16: a model declared tools, never called one,
                     fabricated a result and took ~85 s per turn.

Usage
-----
    python scripts/check_local_models.py
    python scripts/check_local_models.py --json          # machine-readable
    python scripts/check_local_models.py --server URL    # a remote Ollama box
    python scripts/check_local_models.py --tool-probe    # measure tool calling

Exit code is 0 when nothing FAILED (warnings are fine — an unreadable GPU is a
normal machine, not a broken one) and 1 when at least one check failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Run from a source checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OK = "PASS"
WARN = "WARN"
FAIL = "FAIL"

_MARK = {OK: "ok  ", WARN: "warn", FAIL: "FAIL"}


@dataclass
class Check:
    """One verdict, with the facts it was reached from."""

    name: str
    status: str
    detail: str
    facts: dict[str, Any] = field(default_factory=dict)


def _hardware() -> Check:
    """What this machine tells the fit verdicts, and whether it is usable.

    ``0.0 / "none"`` is the honest answer for a GPU the probe cannot read, so
    it is a WARN rather than a FAIL: the models still run, the verdicts just
    fall back to system RAM and will read a discrete AMD card as absent.
    """
    from jarvis.hardware.detection import system_ram_gb, usable_accelerator_gb

    accel, source = usable_accelerator_gb()
    ram = system_ram_gb()
    facts = {
        "os": platform.system(),
        "machine": platform.machine(),
        "accelerator_gb": round(accel, 1),
        "accelerator_source": source,
        "system_ram_gb": ram,
    }
    if accel > 0:
        return Check(
            "hardware",
            OK,
            f"{accel:.1f} GB of accelerator memory read via {source}; "
            f"fit verdicts are judged against the card.",
            facts,
        )
    if ram is None:
        return Check(
            "hardware",
            FAIL,
            "Neither an accelerator nor system memory could be read; every fit "
            "verdict on this machine will say 'unknown'.",
            facts,
        )
    return Check(
        "hardware",
        WARN,
        f"No accelerator this probe can read (it knows NVIDIA via nvidia-smi and "
        f"Apple Silicon unified memory). Fit verdicts fall back to the "
        f"{ram:g} GB RAM rule, so a discrete AMD or Intel card is invisible to "
        f"them even while Ollama uses it.",
        facts,
    )


def _runtime() -> Check:
    """The three-state truth about the server on this OS."""
    from jarvis.brain import ollama_runtime

    status = ollama_runtime.runtime_status()
    facts = {
        k: status.get(k)
        for k in ("installed", "running", "version", "binary", "host_kind", "models_dir")
    }
    if status.get("running"):
        return Check("runtime", OK, str(status.get("detail") or "The server is running."), facts)
    if status.get("installed"):
        return Check(
            "runtime",
            WARN,
            "Ollama is installed but not running; the section offers a Start button "
            "and autostart can do it unattended.",
            facts,
        )
    return Check(
        "runtime",
        WARN,
        "Ollama is not installed on this machine. The section offers the in-app "
        "install; nothing below could be checked against a live server.",
        facts,
    )


async def _inventory(root: str) -> Check:
    """Downloads the section shows, and the aliases it deliberately hides."""
    from jarvis.brain import ollama_inventory as inventory

    try:
        snapshot = await inventory.cached_snapshot(root)
    except Exception as exc:  # noqa: BLE001 — an unreachable server is a verdict, not a crash
        # WARN, not FAIL: a stopped server is the NORMAL state of a fresh user
        # PC, and this script's whole point is to run there. A failure has to
        # mean "something is wrong", or nobody reads the failures.
        return Check("inventory", WARN, f"The server at {root} did not answer: {exc}", {})
    visible = [m.name for m in snapshot.models]
    hidden = sorted(set(snapshot.all_names) - set(visible))
    facts = {"visible": len(visible), "hidden_aliases": hidden, "server": root}
    if not visible:
        return Check(
            "inventory",
            WARN,
            "The server answered but lists no downloads; nothing can be assigned yet.",
            facts,
        )
    return Check(
        "inventory",
        OK,
        f"{len(visible)} download(s) visible, {len(hidden)} Jarvis-internal alias(es) hidden.",
        facts,
    )


async def _roles(root: str, cfg: Any) -> Check:
    """Every slot with its pick, and whether that pick is on disk."""
    from jarvis.brain import ollama_roles

    try:
        states, error = await ollama_roles.list_roles(root, cfg)
    except Exception as exc:  # noqa: BLE001 — report, never raise out of a preflight
        return Check("roles", FAIL, f"The role list could not be built: {exc}", {})
    # A slot pointing at a model the server does not list is only a defect when
    # the server ANSWERED; an unreachable one lists nothing by definition.
    rows = [
        {
            "id": s.spec.id,
            "config_key": s.spec.config_key,
            "writable": s.spec.writable,
            "current": s.current,
            "installed": s.installed,
            "fit": s.current_fit,
        }
        for s in states
    ]
    facts = {"roles": rows, "server_error": error}
    broken = [r for r in rows if r["current"] and not r["installed"]]
    if error:
        return Check("roles", WARN, f"The rows rendered, but the server said: {error}", facts)
    if broken:
        names = ", ".join(f"{r['id']} -> {r['current']}" for r in broken)
        return Check(
            "roles",
            FAIL,
            f"A slot points at a model this server does not list: {names}.",
            facts,
        )
    filled = sum(1 for r in rows if r["current"])
    return Check("roles", OK, f"{filled} of {len(rows)} slot(s) filled, every pick on disk.", facts)


async def _card_parity(root: str) -> Check:
    """The provider card must not offer what the section hides.

    The card builds its picker from the server's raw ``/v1/models``; the
    section folds Jarvis's own derived tags away. A tag on only one side is a
    pick the user can make on the card and then see reported as "Not
    downloaded" on the section — the two surfaces disagreeing about one box.
    """
    from jarvis.brain import ollama_inventory as inventory

    try:
        snapshot = await inventory.cached_snapshot(root)
    except Exception:  # noqa: BLE001 — already reported by the inventory check
        return Check(
            "card-parity",
            WARN,
            "Not checked: the server did not answer, so neither surface has a "
            "list to compare. Start it and run this again.",
            {},
        )
    visible = {m.name for m in snapshot.models}
    offered_by_card = {n for n in snapshot.all_names if not n.endswith(":cloud")}
    only_on_card = sorted(offered_by_card - visible)
    facts = {"only_on_card": only_on_card, "visible": len(visible)}
    if only_on_card:
        return Check(
            "card-parity",
            FAIL,
            f"{len(only_on_card)} tag(s) the provider card offers as a brain are hidden "
            f"from the Local models section: {', '.join(only_on_card)}. Picking one "
            f"leaves the section reporting a model that is on disk as 'Not downloaded'.",
            facts,
        )
    return Check("card-parity", OK, "Both surfaces offer the same models.", facts)


def _autostart(cfg: Any) -> Check:
    """Whether a fresh boot brings the server up with no click."""
    from jarvis.local_models import autostart

    wanted, why = autostart.should_autostart(cfg)
    facts = {"autostart": wanted, "reason": why}
    if wanted:
        return Check("autostart", OK, f"The server comes up with Jarvis ({why}).", facts)
    return Check(
        "autostart",
        WARN,
        f"The server will NOT be started automatically ({why}). That is correct for an "
        f"install that uses no local models; on a machine that does, the first answer "
        f"of the day comes from the cloud fallback.",
        facts,
    )


# ---------------------------------------------------------------------------
# Opt-in behavioural tool probe (``--tool-probe``)
# ---------------------------------------------------------------------------

#: The one fake tool the probe offers. Its answer is knowable only by CALLING
#: it, so a reply that states weather values without a call is a fabrication.
_PROBE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Return the current weather for one city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city name"}
            },
            "required": ["city"],
        },
    },
}

_PROBE_PROMPT = (
    "What is the weather in Istanbul right now? Call the get_weather tool."
)

#: Wordings that betray a RESULT nobody returned: the model answered about the
#: tool or its data without ever emitting a tool call. Live 2026-10-16: an
#: answer of "According to the weather tool … partly sunny 24°C" with no call.
_CONFABULATION_MARKERS: tuple[str, ...] = (
    "get_weather",
    "weather tool",
    "according to the",
    "the tool returned",
    "tool result",
    "tool call",
    "°c",
    "celsius",
    "sunny",
    "cloudy",
    "temperature",
    "wetter",
    "sonnig",
)

def _looks_like_a_text_tool_call(text: str) -> bool:
    """True when the reply IS a tool call, serialized into the text field.

    Live 2026-10-16: two coder models answered the tool request with
    ``{"name": "get_weather", "arguments": {"city": "Istanbul"}}`` as CONTENT.
    That is a real attempt in the wrong channel — Ollama's chat API executes
    only structured ``tool_calls``, so the call never happens. Naming it
    honestly matters: "no tool call" would hide that the model knows what to
    do, and "confabulation" would accuse it of inventing a result it never
    claimed.
    """
    lowered = text.lower()
    if any(marker in lowered for marker in ("<tool_call>", "[tool_call]", "<|tool_call|>")):
        return True
    if not text.strip().startswith("{"):
        return False
    named = any(key in lowered for key in ('"name"', "'name'", "name:"))
    argumented = "argument" in lowered or "parameter" in lowered
    return named and argumented


def classify_probe_response(payload: Any) -> tuple[bool | None, str, str]:
    """What one native ``/api/chat`` answer says about tool calling.

    Returns ``(capable, reason, evidence)``. ``capable=None`` means the answer
    proves NOTHING (an error shape, or an empty reply) — a caller must never
    record that as a verdict, because the runtime gate reads a recorded
    ``False`` as "do not hand this model tools".
    """
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return None, "no_message", ""
    calls = message.get("tool_calls")
    if isinstance(calls, list) and calls:
        name = ""
        first = calls[0]
        if isinstance(first, dict):
            function = first.get("function")
            if isinstance(function, dict):
                name = str(function.get("name") or "")
        return True, "tool_calls", f"called {name or 'a tool'}"
    text = str(message.get("content") or "").strip()
    if not text:
        return None, "empty_reply", ""
    if _looks_like_a_text_tool_call(text):
        return (
            False,
            "tool_call_as_text",
            f"wrote the call as text instead of calling it: {text[:200]}",
        )
    lowered = text.lower()
    if any(marker in lowered for marker in _CONFABULATION_MARKERS):
        return (
            False,
            "confabulation",
            f"stated a tool result without calling: {text[:200]}",
        )
    return False, "no_tool_call", f"answered without calling a tool: {text[:200]}"


async def _probe_one(root: str, model: str) -> tuple[bool | None, str, str]:
    """Send ONE real request carrying the fake tool and read the answer."""
    import httpx

    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": _PROBE_PROMPT}],
        "tools": [_PROBE_TOOL],
        "stream": False,
        # Unload as soon as the answer is in: a probe must not sit on the
        # person's RAM, and the next turn should pay a cold load deliberately.
        "keep_alive": 0,
        "options": {"temperature": 0},
    }
    try:
        # Read generously: a cold local load of a big model can take minutes
        # (live: ~85 s for an 8B Q4). The CONNECT stays short, because a
        # stopped server must not look like a slow one.
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{root}/api/chat", json=body)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001 — an unreachable server is a verdict
        return None, "probe_failed", str(exc)[:200]
    return classify_probe_response(payload)


async def _tool_probe(root: str) -> Check:
    """Measure, per tool-DECLARING download, whether it really calls a tool.

    Opt-in because it loads a model (time and RAM). The verdict is recorded in
    ``jarvis/brain/tool_probe_store.py``, which the runtime gate reads — so a
    model that only CLAIMS tool support stops being handed tools, and a
    corrected model is picked up the moment it is re-probed.
    """
    from jarvis.brain import ollama_inventory as inventory
    from jarvis.brain import tool_probe_store

    try:
        snapshot = await inventory.cached_snapshot(root)
    except Exception as exc:  # noqa: BLE001 — report, never raise out of a preflight
        return Check("tool-probe", WARN, f"The server at {root} did not answer: {exc}", {})

    results: dict[str, Any] = {}
    for model in snapshot.models:
        declared = set(model.capabilities or ())
        if "tools" not in declared:
            continue
        capable, reason, evidence = await _probe_one(root, model.name)
        results[model.name] = {
            "capable": capable,
            "reason": reason,
            "declared": sorted(declared),
        }
        # Record EVERY attempt, including one that proved nothing: ``capable``
        # stays null for those, so the gate ignores it, but the reason and the
        # evidence remain auditable. "Tried and learned nothing" must not look
        # like "never tried".
        tool_probe_store.write_verdict(
            "ollama",
            model.name,
            capable=capable,
            reason=reason,
            evidence=evidence,
            digest=model.digest or None,
        )

    if not results:
        return Check(
            "tool-probe",
            WARN,
            "No download declares tool support, so there was nothing to measure.",
            {"server": root},
        )
    refuted = sorted(n for n, r in results.items() if r["capable"] is False)
    unproven = sorted(n for n, r in results.items() if r["capable"] is None)
    confirmed = len(results) - len(refuted) - len(unproven)
    facts = {"server": root, "results": results, "store": str(tool_probe_store.probe_path())}
    if not refuted and not unproven:
        return Check(
            "tool-probe",
            OK,
            f"Every tool-declaring download called the tool ({confirmed} measured).",
            facts,
        )
    # WARN, not FAIL: a model that overstates itself is a normal (if
    # disappointing) download, and the gate now handles it — the exit code is
    # reserved for a genuinely broken install.
    parts: list[str] = []
    if refuted:
        parts.append(
            f"{len(refuted)} declare tool support but never called the tool: "
            f"{', '.join(refuted)} — the runtime gate now hides tools from them; "
            f"re-run after a re-pull or a model update"
        )
    if unproven:
        parts.append(
            f"{len(unproven)} could not be measured and keep their declaration: "
            f"{', '.join(unproven)}"
        )
    return Check(
        "tool-probe", WARN, f"{'; '.join(parts)}. {confirmed} confirmed capable.", facts
    )


async def run(server: str | None, *, tool_probe: bool = False) -> list[Check]:
    """Every check, in the order a reader wants them."""
    from jarvis.brain.ollama_pull import server_root
    from jarvis.core import config as config_mod

    cfg = config_mod.load_config()
    root = server or server_root()

    checks = [_hardware(), _runtime()]
    checks.append(await _inventory(root))
    checks.append(await _roles(root, cfg))
    checks.append(await _card_parity(root))
    checks.append(_autostart(cfg))
    if tool_probe:
        checks.append(await _tool_probe(root))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--server", default=None, help="Ollama root (default: the configured one)")
    parser.add_argument(
        "--tool-probe",
        action="store_true",
        help=(
            "measure whether every tool-declaring download really calls a tool "
            "(loads ONE model at a time, keep_alive:0, records the verdict and "
            "prints it); off by default"
        ),
    )
    args = parser.parse_args()

    checks = asyncio.run(run(args.server, tool_probe=args.tool_probe))

    if args.json:
        print(json.dumps([asdict(c) for c in checks], indent=2))
    else:
        print(f"Local models preflight — {platform.system()} {platform.machine()}\n")
        for check in checks:
            print(f"[{_MARK[check.status]}] {check.name}")
            print(f"        {check.detail}")
        failed = [c.name for c in checks if c.status == FAIL]
        warned = [c.name for c in checks if c.status == WARN]
        print()
        if failed:
            print(f"FAILED: {', '.join(failed)}")
        if warned:
            print(f"warnings: {', '.join(warned)}")
        if not failed and not warned:
            print("Everything passed.")
    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
