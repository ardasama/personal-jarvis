"""Unit tests for jarvis/mcp/client.py — MCPClient lifecycle.

AP-23 wave-2 finding 10: a stdio MCP server whose launcher binary (typically
``npx``/``node``) is absent from PATH must fail with an actionable message
("install Node.js 18+ ...") instead of a raw ``FileNotFoundError`` string
reaching the plugin badge (caught generically at ``mcp/registry.py``).
"""
from __future__ import annotations

import asyncio
import shutil
from types import SimpleNamespace

import pytest

from jarvis.mcp.client import MCPClient, _stdio_launcher_missing_message
from jarvis.mcp.registry import MCPServerSpec


def _stdio_spec(command: str = "npx", name: str = "some-plugin") -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        display=name.title(),
        description="Test stdio MCP server",
        install_command=[command, "-y", "@example/server"],
        transport="stdio",
    )


# --- _stdio_launcher_missing_message (pure message shaping) -----------------


def test_missing_message_names_node_for_npx() -> None:
    msg = _stdio_launcher_missing_message("some-plugin", "npx")
    assert "Node.js" in msg
    assert "npx" in msg
    assert "some-plugin" in msg


def test_missing_message_names_node_for_node() -> None:
    msg = _stdio_launcher_missing_message("some-plugin", "node")
    assert "Node.js" in msg


def test_missing_message_names_launcher_for_non_node_command() -> None:
    msg = _stdio_launcher_missing_message("docker-plugin", "docker")
    assert "docker" in msg
    assert "docker-plugin" in msg
    # No Node.js hint for a non-Node launcher.
    assert "Node.js" not in msg


# --- MCPClient.start() — actionable failure on a missing launcher -----------


@pytest.mark.asyncio
async def test_start_raises_actionable_error_when_npx_missing(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)
    client = MCPClient(_stdio_spec(command="npx", name="brave-search"))
    with pytest.raises(FileNotFoundError) as excinfo:
        await client.start()
    message = str(excinfo.value)
    # The actionable hint, not a raw errno string like
    # "[Errno 2] No such file or directory: 'npx'".
    assert "Node.js" in message
    assert "18" in message
    assert "brave-search" in message
    assert "Errno" not in message


@pytest.mark.asyncio
async def test_start_actionable_error_is_readable_via_registry_style_format(
    monkeypatch,
) -> None:
    """Mirrors how mcp/registry.py's start_enabled formats the failure:
    ``f"{type(e).__name__}: {e}"``. Must read as an instruction, not a raw
    OS error line.
    """
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)
    client = MCPClient(_stdio_spec(command="npx", name="brave-search"))
    try:
        await client.start()
        pytest.fail("expected start() to raise")
    except Exception as e:  # noqa: BLE001 — mirrors registry.py's catch-all
        formatted = f"{type(e).__name__}: {e}"
    assert "install Node.js 18+" in formatted


@pytest.mark.asyncio
async def test_start_does_not_which_check_when_launcher_present(monkeypatch) -> None:
    """When the launcher IS on PATH, the which()-check must not block startup
    — this test only proves the guard doesn't misfire on a present binary; the
    real transport handshake is exercised by higher-level/integration tests."""
    monkeypatch.setattr(shutil, "which", lambda _cmd: r"C:\fake\npx.cmd")

    class _BoomStdioClient:
        def __init__(self, *_a, **_k) -> None:
            pass

        async def __aenter__(self):
            raise RuntimeError("boom past the which()-check, as expected")

        async def __aexit__(self, *_exc):
            return False

    import mcp.client.stdio as stdio_mod

    monkeypatch.setattr(stdio_mod, "stdio_client", lambda _params, **_kw: _BoomStdioClient())

    client = MCPClient(_stdio_spec(command="npx", name="brave-search"))
    with pytest.raises(RuntimeError, match="boom past the which"):
        await client.start()


# --- MCPClient.stop() — bounded so a wedged transport can't hang teardown ----


@pytest.mark.asyncio
async def test_stop_times_out_instead_of_hanging_on_a_stalled_transport(
    monkeypatch,
) -> None:
    """A cross-task ``anyio`` cancel-scope exit can make
    ``AsyncExitStack.aclose()`` stall for ~20 s before it even errors. ``stop()``
    MUST bound that so a load-bearing teardown (a realtime voice-session end, app
    shutdown) can never hang on it — the live 2026-07-23 bug where a bar-X hangup
    of a realtime session froze the JarvisBar on "listening" and deafened wake
    until the stalled close gave up.
    """
    import jarvis.mcp.client as client_mod

    monkeypatch.setattr(client_mod, "_STOP_TIMEOUT_S", 0.05)

    class _StalledExitStack:
        async def aclose(self) -> None:
            # Never completes — models the wedged transport close.
            await asyncio.Event().wait()

    client = MCPClient(_stdio_spec())
    client._exit_stack = _StalledExitStack()
    client._session = object()

    # Bounded by the test itself, so a regression (unbounded stop) FAILS here
    # instead of hanging the whole suite.
    await asyncio.wait_for(client.stop(), timeout=2.0)

    # The stall was abandoned and the client reset so a later start() is clean.
    assert client._exit_stack is None
    assert client._session is None


@pytest.mark.asyncio
async def test_start_and_stop_keep_contexts_on_one_owner_task(monkeypatch) -> None:
    """Transport contexts stay task-bound across separate public call tasks."""

    context_tasks: list[tuple[str, asyncio.Task[object] | None]] = []

    class _TaskBoundTransport:
        async def __aenter__(self):
            context_tasks.append(("transport-enter", asyncio.current_task()))
            return object(), object()

        async def __aexit__(self, *_exc):
            context_tasks.append(("transport-exit", asyncio.current_task()))

    class _TaskBoundSession:
        def __init__(self, *_args) -> None:
            pass

        async def __aenter__(self):
            context_tasks.append(("session-enter", asyncio.current_task()))
            return self

        async def __aexit__(self, *_exc):
            context_tasks.append(("session-exit", asyncio.current_task()))

        async def initialize(self) -> None:
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])

    import mcp
    import mcp.client.stdio as stdio_mod

    monkeypatch.setattr(shutil, "which", lambda _cmd: r"C:\fake\npx.cmd")
    monkeypatch.setattr(stdio_mod, "stdio_client", lambda _params, **_kw: _TaskBoundTransport())
    monkeypatch.setattr(mcp, "ClientSession", _TaskBoundSession)

    client = MCPClient(_stdio_spec())
    start_task = asyncio.create_task(client.start())
    await start_task
    owner_task = client._owner_task
    assert owner_task is not None
    assert owner_task is not start_task

    stop_task = asyncio.create_task(client.stop())
    await stop_task

    assert [name for name, _task in context_tasks] == [
        "transport-enter",
        "session-enter",
        "session-exit",
        "transport-exit",
    ]
    assert {task for _name, task in context_tasks} == {owner_task}
    assert client._session is None


@pytest.mark.asyncio
async def test_cancelled_stop_finishes_owner_cleanup_and_allows_restart(
    monkeypatch,
) -> None:
    """Caller cancellation cannot strand stale lifecycle state."""

    exit_started = asyncio.Event()
    release_exit = asyncio.Event()

    class _SlowExitTransport:
        async def __aenter__(self):
            return object(), object()

        async def __aexit__(self, *_exc):
            exit_started.set()
            await release_exit.wait()

    class _Session:
        def __init__(self, *_args) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return None

        async def initialize(self) -> None:
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])

    import mcp
    import mcp.client.stdio as stdio_mod

    monkeypatch.setattr(shutil, "which", lambda _cmd: r"C:\fake\npx.cmd")
    monkeypatch.setattr(stdio_mod, "stdio_client", lambda _params, **_kw: _SlowExitTransport())
    monkeypatch.setattr(mcp, "ClientSession", _Session)

    client = MCPClient(_stdio_spec())
    await client.start()
    owner = client._owner_task
    assert owner is not None

    stop_task = asyncio.create_task(client.stop())
    await exit_started.wait()
    stop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop_task

    release_exit.set()
    await asyncio.wait_for(asyncio.shield(owner), timeout=1.0)
    assert client._owner_task is None
    assert client._session is None

    await client.start()
    assert client._session is not None
    await client.stop()


# --- stdio stderr capture: a start failure must name its real cause ----------


def test_describe_exception_flattens_a_group() -> None:
    """The top-level ExceptionGroup string is useless in a log; the leaf shows."""
    import jarvis.mcp.client as client_mod

    group = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [RuntimeError("llama-server binary not found"), ValueError("bad arg")],
    )
    described = client_mod._describe_exception(group)
    assert "llama-server binary not found" in described
    assert "bad arg" in described
    # No leftover wrapper noise.
    assert "TaskGroup" not in described


def test_describe_start_failure_keeps_type_when_nothing_to_add() -> None:
    """A plain failure with no stderr keeps its original type/identity."""
    import jarvis.mcp.client as client_mod

    original = FileNotFoundError("brave-search: install Node.js 18+")
    assert client_mod._describe_start_failure(original, "") is original


def test_registry_error_includes_stderr_tail_once() -> None:
    """The badge-facing error string carries the captured stderr exactly once."""
    from jarvis.mcp.registry import _with_stderr

    class _Client:
        last_stderr_tail = "boom: missing native dep"

    first = _with_stderr("RuntimeError: Connection closed", _Client())
    assert "boom: missing native dep" in first
    # Idempotent: a message that already carries the tail is not doubled.
    assert _with_stderr(first, _Client()) == first


def test_registry_error_without_tail_is_unchanged() -> None:
    from jarvis.mcp.registry import _with_stderr

    class _Client:
        last_stderr_tail = ""

    assert _with_stderr("RuntimeError: Connection closed", _Client()) == (
        "RuntimeError: Connection closed"
    )


@pytest.mark.asyncio
async def test_start_failure_surfaces_the_child_stderr() -> None:
    """A stdio server that dies during the handshake must surface WHY.

    Regression for the live ``filesystem`` failure: every start used to report
    only ``Startfehler: Connection closed`` because the child's stderr went to
    ``sys.stderr`` (``None`` in the windowed desktop app). The child here writes
    a reason and exits non-zero — that reason must reach ``str(error)`` and
    ``client.last_stderr_tail``.
    """
    import sys

    spec = MCPServerSpec(
        name="dies-at-handshake",
        display="Dies",
        description="exits before initialize",
        install_command=[
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('BOOM-REASON-42'); "
            "sys.stderr.flush(); sys.exit(3)",
        ],
        transport="stdio",
    )
    client = MCPClient(spec)
    with pytest.raises(Exception) as excinfo:
        await client.start()

    assert "BOOM-REASON-42" in str(excinfo.value)
    assert "BOOM-REASON-42" in client.last_stderr_tail
    # The useless wrapper string must not be all we say.
    assert "sub-exception" not in str(excinfo.value)


# --- call_tool revives a client that outlived its server --------------------


@pytest.mark.asyncio
async def test_call_tool_revives_a_stopped_client() -> None:
    """An adapter whose server dropped must get one bounded restart, not a
    permanent 'MCPClient not started' (the live browseros-neo symptom)."""
    calls: list[str] = []

    class _Session:
        async def call_tool(self, name, args):
            calls.append(name)
            return SimpleNamespace(isError=False, content=[])

    client = MCPClient(_stdio_spec(name="browseros-neo"))

    async def _fake_start() -> None:
        calls.append("start")
        client._session = _Session()

    client.start = _fake_start  # type: ignore[method-assign]

    result = await client.call_tool("tabs", {})

    assert calls == ["start", "tabs"]
    assert result is not None


@pytest.mark.asyncio
async def test_call_tool_backs_off_after_a_failed_revive() -> None:
    """A dead server is not re-restarted (nor re-charged the timeout) per call."""
    attempts = 0

    client = MCPClient(_stdio_spec(name="dead-server"))

    async def _failing_start() -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("Connection closed")

    client.start = _failing_start  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="MCPClient not started"):
        await client.call_tool("tabs", {})
    assert attempts == 1

    # Within the backoff window the second call must NOT restart again.
    with pytest.raises(RuntimeError, match="retry in"):
        await client.call_tool("tabs", {})
    assert attempts == 1


def test_not_started_message_includes_captured_stderr() -> None:
    client = MCPClient(_stdio_spec(name="filesystem"))
    client.last_stderr_tail = "missing native dep"
    message = client._not_started_message()
    assert "MCPClient not started" in message
    assert "missing native dep" in message


def test_not_started_message_without_reason_is_plain() -> None:
    client = MCPClient(_stdio_spec(name="filesystem"))
    assert client._not_started_message() == "filesystem: MCPClient not started"
