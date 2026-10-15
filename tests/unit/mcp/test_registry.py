"""Unit tests for the MCP registry.

Since 2026-04-22, ``BOOTSTRAP_SERVERS`` is deliberately empty — all servers
come from ``mcp.json`` (user-editable or via Claude Desktop import).
The tests therefore cover the registry mechanics, not a curated
server list.
"""
from __future__ import annotations

import pytest

from jarvis.mcp.registry import BOOTSTRAP_SERVERS, MCPRegistry, MCPServerSpec


def _make_spec(name: str = "custom-mcp", *, mandatory: bool = False) -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        display=name.title(),
        description="Test spec",
        install_command=["echo", "hi"],
        mandatory=mandatory,
    )


def test_bootstrap_servers_is_empty_by_design() -> None:
    """Deliberate architecture decision from 2026-04-22: no
    pre-curated servers — all servers come from ``mcp.json``."""
    assert BOOTSTRAP_SERVERS == []


def test_registry_starts_empty() -> None:
    reg = MCPRegistry()
    assert reg.all_specs() == []


def test_registry_register_spec_adds_new_entry() -> None:
    reg = MCPRegistry()
    spec = _make_spec("custom-mcp")
    reg.register_spec(spec)
    assert reg.get_spec("custom-mcp") is spec
    assert len(reg.all_specs()) == 1


def test_registry_register_spec_overwrites_same_name() -> None:
    reg = MCPRegistry()
    original = _make_spec("filesystem-mcp")
    reg.register_spec(original)
    replaced = MCPServerSpec(
        name="filesystem-mcp",
        display="FS-OVERRIDE",
        description="overridden",
        install_command=["override"],
    )
    reg.register_spec(replaced)
    assert reg.get_spec("filesystem-mcp").display == "FS-OVERRIDE"
    assert len(reg.all_specs()) == 1


def test_registry_get_spec_returns_none_for_unknown() -> None:
    reg = MCPRegistry()
    assert reg.get_spec("nonexistent-mcp") is None


def test_registry_all_specs_returns_all_registered() -> None:
    reg = MCPRegistry()
    reg.register_spec(_make_spec("a-mcp"))
    reg.register_spec(_make_spec("b-mcp"))
    names = {s.name for s in reg.all_specs()}
    assert names == {"a-mcp", "b-mcp"}


def test_mcp_server_spec_is_frozen() -> None:
    """Specs are pydantic-frozen — mutation must fail."""
    spec = _make_spec()
    with pytest.raises((AttributeError, Exception)):
        spec.name = "changed"  # type: ignore[misc]


def test_registry_active_clients_initially_empty() -> None:
    reg = MCPRegistry()
    assert reg.active_clients() == {}


def test_registry_active_names_agrees_with_active_clients() -> None:
    """``active_names()`` is the live-state introspection the manage-mcp-server
    tool reads; it must never disagree with ``active_clients()``.

    Regression guard for the audit finding in
    ``docs/reports/jarvis-mcp-deep-dive-2026-08-08.md`` §3 item 1: the tool
    called a method that did not exist, the AttributeError was swallowed, and
    every MCP enable reported "restart required" even when the server had
    actually started live.
    """
    reg = MCPRegistry()
    assert reg.active_names() == []
    assert reg.active_names() == list(reg.active_clients().keys())

    reg._clients["filesystem"] = object()  # type: ignore[assignment]
    reg._clients["notion"] = object()  # type: ignore[assignment]
    assert set(reg.active_names()) == {"filesystem", "notion"}
    assert set(reg.active_names()) == set(reg.active_clients().keys())


def test_registry_active_names_is_a_copy_not_a_view() -> None:
    """Mutating the returned list must not touch the registry's client map."""
    reg = MCPRegistry()
    reg._clients["github"] = object()  # type: ignore[assignment]
    names = reg.active_names()
    names.append("injected")
    assert reg.active_names() == ["github"]


@pytest.mark.asyncio
async def test_registry_stop_all_is_safe_when_empty() -> None:
    reg = MCPRegistry()
    await reg.stop_all()
    assert reg.active_clients() == {}
