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
