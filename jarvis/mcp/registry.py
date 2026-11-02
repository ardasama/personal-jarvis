"""MCP server registry: specs and runtime management of active clients.

``MCPServerSpec`` describes an installable MCP server (install command,
auth keys, mandatory/optional). The global ``BOOTSTRAP_SERVERS`` list is
the authoritative catalogue of all servers offered during the first-run
wizard. ``MCPRegistry`` holds the active clients at runtime and can start
or stop them as a group.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .client import MCPClient

log = logging.getLogger(__name__)

# Per-server start ceiling (seconds). A server that hangs on initialize /
# list_tools must not hang its start task forever — mirrors the 60 s guard in
# ``bootstrap.verify_server``. On expiry we log per-server and move on; the
# parallel start of the other servers is never aborted.
_START_TIMEOUT_S = 60.0


# ----------------------------------------------------------------------
# Spec
# ----------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MCPServerSpec:
    """Describes an installable MCP server (static, immutable)."""

    name: str                               # internal ID, e.g. "filesystem-mcp"
    display: str                            # user-facing display name
    description: str                        # one-line description
    install_command: list[str]              # argv for subprocess (uvx/npx/...)
    required_auth: list[str] = field(default_factory=list)  # keyring-Keys
    transport: Literal["stdio", "sse", "http"] = "stdio"
    mandatory: bool = False
    platform_notes: str = ""
    # Remote-transport endpoint (http/sse). Unused for stdio.
    url: str | None = None
    # HTTP headers for the http transport. Values may contain ``$SECRET``
    # placeholders resolved against the Credential Manager at connect time.
    headers: dict[str, str] = field(default_factory=dict)
    # Start this stdio server WITHOUT the process environment (see
    # ``jarvis.mcp.env_isolation``). Set for servers whose command line came
    # from someone other than the user — a community plugin would otherwise
    # inherit every API key the owner ever exported. Off by default: a server
    # from the user's own mcp.json is theirs, and cutting its environment
    # would break the many that read a token straight out of it.
    isolate_env: bool = False


# ----------------------------------------------------------------------
# BOOTSTRAP_SERVERS
# ----------------------------------------------------------------------
# Intentionally empty: user decision 2026-04-22. The previously pre-curated
# 8 servers (filesystem-mcp, git-mcp, memory-mcp, windows-mcp, gmail-mcp, ...)
# were a promise that was not kept — some uvx/npx packages do not exist under
# those names and OAuth flows were missing. All servers now come exclusively
# from mcp.json, which the user edits directly or via Claude Desktop import.
BOOTSTRAP_SERVERS: list[MCPServerSpec] = []


# ----------------------------------------------------------------------
# Runtime-Registry
# ----------------------------------------------------------------------

class MCPRegistry:
    """Holds specs and active clients; starts and stops them as a group."""

    def __init__(self) -> None:
        # Specs are stored as a dict keyed by name — third-party specs can
        # be registered at runtime (for tests and plugin extensions).
        self._specs: dict[str, MCPServerSpec] = {s.name: s for s in BOOTSTRAP_SERVERS}
        self._clients: dict[str, MCPClient] = {}
        # Last start error per server name so the UI can show a concrete
        # reason instead of just "not running".
        self._errors: dict[str, str] = {}

    # ---- Specs --------------------------------------------------------

    def register_spec(self, spec: MCPServerSpec) -> None:
        """Register an additional spec (overwrites an existing one with the same name)."""
        self._specs[spec.name] = spec

    def all_specs(self) -> list[MCPServerSpec]:
        """List of all known specs (mandatory + optional, including registered ones)."""
        return list(self._specs.values())

    def get_spec(self, name: str) -> MCPServerSpec | None:
        return self._specs.get(name)

    # ---- mcp.json-Integration ----------------------------------------

    def load_from_mcp_json(self) -> None:
        """Load user overrides and custom servers from ``mcp.json``.

        - Entries with ``command`` override/extend bootstrap specs.
        - Entries WITHOUT ``command`` (pure enable overrides) are left
          at the existing bootstrap spec and are not touched here.
        """
        from .state import load_config  # lazy, prevents circular import

        cfg = load_config()
        for name, entry in cfg.get("mcpServers", {}).items():
            if not isinstance(entry, dict):
                continue
            transport = entry.get("transport", "stdio")
            command = entry.get("command")
            url = entry.get("url")
            if transport == "http":
                # Remote HTTP servers carry a ``url`` instead of a subprocess
                # ``command``; without one there is nothing to connect to.
                if not url:
                    continue
                install_command: list[str] = []
            else:
                if not command:
                    continue
                install_command = [command, *list(entry.get("args", []))]
            try:
                spec = MCPServerSpec(
                    name=name,
                    display=entry.get("display") or name.replace("-", " ").title(),
                    description=entry.get("description", ""),
                    install_command=install_command,
                    required_auth=list(entry.get("required_auth", [])),
                    transport=transport,
                    mandatory=False,
                    platform_notes=entry.get("platform_notes", ""),
                    url=url,
                    headers=dict(entry.get("headers", {})),
                )
            except (TypeError, ValueError) as exc:
                log.warning("mcp.json[%s] invalid: %s", name, exc)
                continue
            self._specs[name] = spec

    # ---- Error-Tracking ----------------------------------------------

    def last_error(self, name: str) -> str | None:
        """Last stored start error for a server, or None."""
        return self._errors.get(name)

    def clear_error(self, name: str) -> None:
        self._errors.pop(name, None)

    # ---- Clients ------------------------------------------------------

    def active_clients(self) -> dict[str, MCPClient]:
        """Mapping of name → MCPClient for all currently running clients."""
        return dict(self._clients)

    def active_names(self) -> list[str]:
        """Names of all currently running MCP clients.

        Public introspection, because ``jarvis.plugins.tool.manage_mcp_server``
        must decide whether an enable/disable took effect live. Without it the
        call raised ``AttributeError``, the tool's ``except Exception`` swallowed
        it, and every enable reported "restart required" even when the server had
        actually started — or, on the disable path, claimed the drop had applied
        live when it had not. See
        ``docs/reports/jarvis-mcp-deep-dive-2026-08-08.md`` §3 item 1.

        Delegates to :meth:`active_clients` so the client map keeps exactly one
        read path; the caller list and the client map can never disagree.
        """
        return list(self.active_clients().keys())

    async def start_enabled(self, enabled_names: list[str]) -> None:
        """Start all specified servers in parallel. Errors are logged and stored
        per server in ``self._errors``, but the overall start is not aborted —
        a single broken server must not block the entire pipeline.
        """
        from .client import MCPClient  # local import to avoid circular dependency
        from .notification_filter import install_notification_log_filter

        # A server may emit a non-standard notification method (observed live:
        # ``method='log'``) that the SDK's strict ``ServerNotification`` union
        # rejects, spamming the log with a 19-error Pydantic dump per frame.
        # Installing the tolerant filter before any client starts keeps that
        # quiet (idempotent — safe to call on every start).
        install_notification_log_filter()

        async def _start_one(spec: MCPServerSpec) -> None:
            # Pull env overrides from mcp.json — allows setting OAuth tokens
            # or API keys per server without code changes.
            env_overrides = _env_from_mcp_json(spec.name)
            client = MCPClient(spec, env_overrides=env_overrides)
            try:
                # Per-server start timeout: a server hanging on initialize /
                # list_tools must not block this task forever. asyncio.wait_for
                # cancels the hung start on expiry and raises TimeoutError, which
                # the ``except`` below records per server — the gather over the
                # other servers keeps running, so one hung server never stalls
                # the parallel boot.
                await asyncio.wait_for(client.start(), timeout=_START_TIMEOUT_S)
                self._clients[spec.name] = client
                self._errors.pop(spec.name, None)
                log.info("MCP server %s started", spec.name)
            except TimeoutError:
                error_msg = f"start timeout ({_START_TIMEOUT_S:.0f}s)"
                error_msg = _with_stderr(error_msg, client)
                self._errors[spec.name] = error_msg
                log.error("MCP-Server %s Startfehler: %s", spec.name, error_msg)
            except Exception as e:  # noqa: BLE001
                error_msg = _with_stderr(f"{type(e).__name__}: {e}", client)
                self._errors[spec.name] = error_msg
                log.error("MCP-Server %s Startfehler: %s", spec.name, error_msg)

        tasks = [
            _start_one(self._specs[n])
            for n in enabled_names
            if n in self._specs
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=False)
        # AIHub P04: optional, safe hibernation for verified stateless MCP
        # clients. All tools stay registered; the existing MCPClient revives
        # on first call. No extra daemon/process. Disabled unless mcp.json
        # explicitly selects idle_hibernate_seconds on allowlisted servers.
        try:
            import json as _p04_json
            from pathlib import Path as _p04_Path
            _p04_config = _p04_Path(__file__).resolve().parents[2] / "mcp.json"
            _p04_settings = _p04_json.loads(_p04_config.read_text(encoding="utf-8-sig"))
            if any(
                isinstance(_p04_entry, dict)
                and "idle_hibernate_seconds" in _p04_entry
                for _p04_entry in _p04_settings.get("mcpServers", {}).values()
            ):
                import importlib.util as _p04_import
                _p04_file = _p04_Path.home() / "AIHub" / "projects" / "AIHub-Evolution" / "P04-JarvisMCPIdleSupervisor.py"
                _p04_spec = _p04_import.spec_from_file_location("aihub_mcp_idle_supervisor", _p04_file)
                if _p04_spec is None or _p04_spec.loader is None:
                    raise RuntimeError("P04_IDLE_SUPERVISOR_UNAVAILABLE")
                _p04_mod = _p04_import.module_from_spec(_p04_spec)
                _p04_spec.loader.exec_module(_p04_mod)
                _p04_mod.install(self, config_path=_p04_config)
        except Exception as _p04_error:
            log.warning("AIHub P04 idle-MCP supervision disabled: %s", type(_p04_error).__name__)

    async def start_one(self, name: str) -> bool:
        """Start a single registered server; True when it is live afterwards.

        Idempotent — an already-running server is left alone. Reuses
        :meth:`start_enabled`, so a per-server failure lands in :attr:`_errors`
        with the captured stderr exactly as it does at boot.
        """
        if name in self._clients:
            return True
        if name not in self._specs:
            return False
        await self.start_enabled([name])
        return name in self._clients

    async def stop_one(self, name: str) -> bool:
        """Stop and forget one running server; True when it is gone afterwards.

        The half that made a live *disable* dishonest: with no per-server stop
        the registry still answered "running", so disabling a server had to
        demand an app restart even when nothing needed one. The client is kept
        when its own (self-bounded) stop fails, so the caller can still ask for
        a restart instead of claiming a live success that did not happen.
        """
        client = self._clients.get(name)
        if client is None:
            return True
        try:
            await asyncio.wait_for(client.stop(), timeout=_START_TIMEOUT_S)
        except TimeoutError:
            log.warning(
                "MCP server %s stop timed out after %.0fs", name, _START_TIMEOUT_S
            )
            return False
        except Exception as e:  # noqa: BLE001
            log.warning("MCP server %s stop error: %s", name, e)
            return False
        self._clients.pop(name, None)
        self._errors.pop(name, None)
        log.info("MCP server %s stopped", name)
        return True

    async def stop_all(self) -> None:
        """Stop all active clients in parallel (best effort)."""
        clients = list(self._clients.values())
        self._clients.clear()
        if not clients:
            return
        await asyncio.gather(
            *(c.stop() for c in clients),
            return_exceptions=True,
        )


def _with_stderr(message: str, client: Any) -> str:
    """Append a failed client's captured server stderr, exactly once.

    ``MCPClient`` already folds stderr into the exception it raises, but a
    start *timeout* raises inside ``asyncio.wait_for`` with no such exception,
    and the plugin badge reads ``self._errors`` — so the tail is appended here
    unless the message already carries it.
    """
    tail = getattr(client, "last_stderr_tail", "")
    if tail and "server stderr:" not in message:
        return f"{message} | server stderr: {tail}"
    return message


def _env_from_mcp_json(name: str) -> dict[str, str] | None:
    """Read the ``env`` block from mcp.json for a server, or None.

    Values that start with ``$`` are resolved via ``get_secret()``
    (e.g. ``"$GMAIL_OAUTH_TOKEN"`` → lookup in the Credential Manager).
    """
    from jarvis.core.config import get_secret

    from .state import get_server_entry

    entry = get_server_entry(name)
    if not entry:
        return None
    raw_env = entry.get("env") or {}
    if not isinstance(raw_env, dict) or not raw_env:
        return None

    resolved: dict[str, str] = {}
    for key, value in raw_env.items():
        if not isinstance(value, str):
            continue
        if value.startswith("$"):
            secret_key = value[1:]
            looked_up = get_secret(secret_key, env_fallback=secret_key)
            if looked_up:
                resolved[key] = looked_up
                continue
            log.warning("env[%s]=%s could not be resolved for MCP %s",
                        key, value, name)
            continue
        resolved[key] = value
    return resolved or None
