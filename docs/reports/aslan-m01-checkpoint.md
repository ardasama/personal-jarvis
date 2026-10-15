# ASLAN-M01 — Personal Jarvis reliability checkpoint

Rolling engineering record for the "make the real product reliable, then let it
evolve" effort. One section per cycle; older sections are never rewritten.

## Verified environment (2026-10-16)

| Fact | Value | Evidence |
|---|---|---|
| Product install | `C:\Users\Arda\.personal-jarvis` | `.jarvis-managed-install` (`profile: full`, `desktop: true`) |
| Desktop entry | `.venv\Scripts\PersonalJarvis.exe -m jarvis.ui.web.launcher` | `Desktop\Personal Jarvis.lnk` |
| Runtime data | `<repo>\data\`, `%LOCALAPPDATA%\Jarvis\` | live SQLite + JSON state |
| Python | 3.12.9 (project `.venv`) | `.venv\Scripts\python.exe -V` |
| Runtime brain | `gemini` (realtime `gemini-live`, worker `antigravity`) | `jarvis.toml` |
| Logs | `data\jarvis_desktop.log` (9.4 MB), `data\flight_recorder\*.jsonl` | live |

Not the product (checked and excluded): `C:\AI\Jiku` (empty git dir),
`C:\AI-Agents` (separate "AI File Sentinel"), `C:\MORPHOS`, `C:\AI\*`.

## Cycle 1 — MCP start-failure diagnosability  (IMPLEMENTED · TESTED)

**Symptom.** `data\jarvis_desktop.log` shows `MCP-Server filesystem Startfehler:
Connection closed` ten times, and `browseros-neo` failing with `MCPClient not
started` / `timed out after 20s`. The message names nothing actionable.

**Root cause (confirmed).** The MCP SDK routes a stdio server's stderr to
`errlog`, which defaults to `sys.stderr` — `None` in the windowed desktop app.
So a server that dies during the handshake leaves no reason behind. Worse, the
failure arrives as an `ExceptionGroup` whose `str()` is only
"unhandled errors in a TaskGroup (1 sub-exception)". `registry.py` logged
`str(e)`, so both the child's words and the real leaf cause were lost.

Reproduced in isolation: a child that writes to stderr and exits produces
`ExceptionGroup` while the same run with a real `errlog` file captures the text.

**Change.**
- `jarvis/mcp/client.py` — stdio transport now opens a `TemporaryFile` as
  `errlog` (real `fileno`, stays open for the client's life), stores the tail in
  `MCPClient.last_stderr_tail`, and raises a `RuntimeError` carrying the
  flattened exception chain plus `server stderr: …` (`__cause__` preserved).
  New helpers `_open_stderr_capture`, `_read_stderr_tail`,
  `_close_stderr_capture`, and module-level `_describe_exception`,
  `_describe_start_failure`. A failure with nothing to add keeps its original
  type (the missing-launcher `FileNotFoundError` path is unchanged).
- `jarvis/mcp/registry.py` — the per-server `_errors` entry (what the plugin
  badge reads) appends the captured stderr once, via `_with_stderr`; the timeout
  branch gets it too.
- `tests/unit/mcp/test_mcp_client.py` — 5 new tests (group flattening, type
  preservation, registry tail idempotence/passthrough, and a real short-lived
  child whose stderr must reach `str(error)`); 3 existing stubs updated for the
  new `stdio_client(params, errlog=…)` call.

**Verification.** `pytest tests/unit/mcp` → 123 passed; `ruff check` on the three
touched files → clean. Exact commands:
`uv run --no-project --python .\.venv\Scripts\python.exe --with pytest --with
pytest-asyncio -- pytest tests/unit/mcp -q` and the `--with ruff` variant.
(pytest/ruff are run from an ephemeral uv overlay; the user's `.venv` is never
installed into — BUG-219.)

**Safety.** No file deleted. Originals of the three touched files were copied to
`%TEMP%\opencode\aslan-m01\<ts>\` before editing; git also holds the base.

**Unverified / limits.** The fix was proven against a synthetic child and the
existing suite. It has **not** yet been observed against the live `filesystem`
server (that needs a desktop-app restart, deliberately not forced from a coding
session). `browseros-neo`'s `MCPClient not started` is a separate lifecycle bug,
still open.

**Next action.** Restart the desktop app once and read the new stderr line for
`filesystem`; then fix the `browseros-neo` enable/disable lifecycle
(reconcile desired config → live state).

## Cycle 2 — revive an MCP client that outlived its server  (IMPLEMENTED · TESTED)

**Symptom.** `MCPTool browseros-neo/tabs error … browseros-neo: MCPClient not
started` (5×) and one `timed out after 20s`. The server *had* started earlier in
the same session (`MCPClient[browseros-neo] ready`), so the tool adapter existed
while its client's transport was dead.

**Root cause (confirmed).** Adapters are created from `active_clients()` at
start; nothing removes them when a client later stops or is deleted (also
flagged in `docs/reports/jarvis-mcp-deep-dive-2026-08-08.md` §3 item 2). The
adapter keeps a reference to the dead client, and every call hit
`call_tool`'s straight `raise RuntimeError("MCPClient not started")`.

**Change.** `jarvis/mcp/client.py` — `call_tool` now calls a new
`_ensure_started()` when there is no session: one bounded restart
(`_LAZY_START_TIMEOUT_S`, default 15 s, `JARVIS_MCP_START_TIMEOUT_S`), then a
60 s backoff after a failed attempt so a dead server is not re-charged the
timeout on every later call. `_not_started_message()` reports the real reason
plus the captured stderr. A genuine failure still fails fast and honestly.

**Verification.** `pytest tests/unit/mcp` → 127 passed; `ruff check` clean.
4 new tests: revive path, backoff-once, and the two message shapes.

**Next action.** MCP config→live **reconcile** (one idempotent operation):
enable/disable must prove the connection and atomically add/remove clients,
tool adapters, capabilities and the `BrainToolsChanged` signal — so a stale
adapter like the one above is cleaned up instead of relying on a lazy revive.

## Cycle 3 — wake-model store resolved from the wrong directory  (IMPLEMENTED · TESTED)

**Status note.** The *crash* was already fixed before this mission: commit
`4cde1f9` ("an unreadable Vosk folder must not crash the wake plan") added
`_safe_subdirs`, and `VOICE OFFLINE` lines stopped after 2026-10-15 04:52. The
later `Access is denied` lines are the graceful warning only. Nothing was
re-fixed — the *path* defect underneath was still there.

**Root cause (confirmed).** `wake_constants._vosk_models_root` and
`wake_model_fetch._models_root` both resolved the store as
`os.environ.get("JARVIS__MEMORY__DATA_DIR") or "data"` — a path relative to the
process CWD, and without the instance suffix. The desktop shortcut's "start in"
is the user's home, so an unset override lists `<home>/data/wake_models/vosk`
instead of the checkout's data dir (live: `PermissionError: [WinError 5] Access
is denied: 'data\wake_models\vosk\en'`), and `JARVIS_INSTANCE=dev` never got the
`data-dev` directory that `jarvis.core.config.DATA_DIR` uses.

**Change.** New stdlib-only `_data_dir_base()` in `wake_constants` mirrors
`config._resolve_data_dir` (override verbatim → `JARVIS_DATA_DIR` → repo path +
`data`/`data-dev`); `_vosk_models_root` uses it; `wake_model_fetch._models_root`
delegates to it so the fetch target and the read target cannot diverge (its own
docstring demands that).

**Verification.** 6 new tests in `tests/unit/speech/test_wake_models_root.py`
(absolute, explicit override, CWD-independence, instance suffix, fetch/read
parity, explicit-dir passthrough) → **6 passed**. `ruff` clean on all changed
files; the 2 `E501`s it reports in `wake_constants.py` are pre-existing in HEAD
(German whisper-noise regex, untouched).

**Next action.** MCP config→live reconcile (deep-dive Wave 2).

**Follow-up (same series, done).** `jarvis/speech/local_models.py`
`models_root()` carried the identical `or "data"` fallback and now shares
`_data_dir_base` too — all three speech-model paths (wake store, wake fetch,
local models) resolve from one base. Test file now 8 tests, ruff clean.

## Cycle 4 — a per-server stop, so `disable` can be honest  (IMPLEMENTED · TESTED)

**Symptom.** The chat/voice tool logged `enable 'filesystem' (live=False
restart=True)` and a disable could only ever answer "restart required" — the
deep-dive (`docs/reports/jarvis-mcp-deep-dive-2026-08-08.md` §3 item 1) named
the missing half: the registry starts servers as a *group* and has no
per-server stop, so a running client could not be dropped live.

**Change.**
- `jarvis/mcp/registry.py` — new `start_one(name)` (idempotent; reuses
  `start_enabled` so per-server errors still land in `_errors` with the Cycle-1
  stderr) and `stop_one(name)` (bounded by `_START_TIMEOUT_S`; only forgets the
  client and clears its error **after** a successful stop — a wedged transport
  is kept so the caller can still ask for a restart).
- `jarvis/plugins/tool/manage_mcp_server.py` — the disable branch now calls
  `registry.stop_one(name)` for a live disable; a missing registry or a failing
  stop still reports `requires_restart=True` honestly.

**Verification.** `pytest tests/unit/mcp` → **132 passed** (5 new: start_one
unregistered/idempotent, stop_one forgets + clears the stale error, stop_one
no-op, stop_one keeps a client whose stop raised). `ruff` clean.

**Next action.** Reconcile the tool adapters/capabilities too: a stopped or
removed server must drop its `MCPToolAdapter` entries and publish one
`BrainToolsChanged`, so no stale adapter is left for the lazy revive (Cycle 2)
to paper over.

## Cycle 5 — REST disable/stop/delete stop honestly  (IMPLEMENTED · TESTED)

**Finding (the Cycle-4 "next action" was partly wrong — corrected here).** The
adapter leak flagged in the deep-dive is already handled in the current code:
`McpToolLoader.expand()` rebuilds one `MCPToolAdapter` per tool of every
`active_clients()` entry, and `mcp_routes` already publishes `BrainToolsChanged`
on enable/disable/delete. So no stale adapter survives. What *was* wrong: the
routes stopped a client by reaching into the private map
(`registry._clients.pop`, three `# noqa: SLF001` sites) and always answered
`stopped: True` / `status: "stopped"` even when the stop had raised.

**Change.** `jarvis/ui/web/mcp_routes.py` — `disable_mcp`, `stop_mcp` and
`delete_mcp` now call `registry.stop_one(name)` (Cycle 4) and report the real
outcome (`stopped` false, or `status: "failed"`, when the stop did not take).
The probe cleanup's silent `except Exception: pass` now logs its cause (AP-30).
The private `_clients.pop` calls in those three paths are gone.

**Verification.** `pytest tests/unit/ui/test_mcp_routes_events.py tests/unit/mcp`
→ **137 passed** (3 new: disable stops through the registry, disable reports a
failed stop honestly, stop reports `failed`). `ruff` on `mcp_routes.py` is now
**clean** — it carried 2 `S110` (silent `except: pass`) at HEAD; both are gone.

**Next action.** Provider independence: the remaining engine failures in the
live log are `Ollama llama-server binary not found`, invalid Grok/OpenAI keys
and Gemini free-tier quota — trace the fallback chain so a missing or failing
provider degrades across families (AP-22) instead of surfacing the last raw
error.
