"""One connected MCP server behind a single tool.

Live 2026-08-27: 221 tools (131 of them from three connected servers) exceeded
a 32k window, and the user read "check the network". Live 2026-10-16: the trim
then hid 92 of 92 tools — a local model had none at all ("budget for tools 0").
Folding each server's tools into ONE façade keeps the whole server reachable
for a fraction of the tokens, and it happens BEFORE the trim, so the trim is
the second resort instead of the first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from jarvis.brain.manager import (
    _CONTEXT_FIT_RESERVE_TOKENS,
    BrainManager,
    MCPToolFacade,
    _fit_tools_to_context_window,
    _fold_largest_mcp_group,
    _fold_mcp_surface,
    _tool_surface_tokens,
)
from jarvis.core.protocols import ToolResult


def _pad(size: int) -> dict[str, Any]:
    props = {f"arg{i}": {"type": "string", "description": "x" * 40} for i in range(size)}
    return {"type": "object", "properties": props}


@dataclass
class _FakeTool:
    name: str
    description: str = "does a thing"
    schema: dict[str, Any] = field(default_factory=lambda: _pad(0))
    is_mcp_tool: bool = False
    is_action_tool: bool = True
    risk_tier: str = "monitor"
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def execute(self, args: dict[str, Any], ctx: Any) -> ToolResult:
        self.calls.append(dict(args))
        return ToolResult(success=True, output={"echo": args})


def _mcp(name: str, **kwargs: Any) -> _FakeTool:
    return _FakeTool(name=name, is_mcp_tool=True, **kwargs)


# ------------------------------------------------------------- the façade


def test_a_facade_lists_its_members_and_inherits_the_highest_tier() -> None:
    facade = MCPToolFacade(
        "github",
        [
            _mcp("github/get_issue", risk_tier="safe"),
            _mcp("github/create_issue", risk_tier="ask"),
        ],
    )
    assert facade.name == "github/_tools"
    assert facade.risk_tier == "ask"
    assert set(facade.member_names) == {"get_issue", "create_issue"}
    assert set(facade.schema["properties"]["tool"]["enum"]) == {"get_issue", "create_issue"}
    assert "create_issue" in facade.description
    assert facade.is_action_tool is True
    # NOT an individually droppable server addition: the façade is what keeps
    # the server reachable, so the trim must not take it first.
    assert facade.is_mcp_tool is False
    assert facade.is_mcp_facade is True


@pytest.mark.asyncio
async def test_the_facade_delegates_to_the_named_member() -> None:
    read = _mcp("srv/read")
    write = _mcp("srv/write")
    facade = MCPToolFacade("srv", [read, write])

    result = await facade.execute({"tool": "write", "arguments": {"body": "hi"}}, None)

    assert result.success is True
    assert write.calls == [{"body": "hi"}]
    assert read.calls == []


@pytest.mark.asyncio
async def test_an_unknown_member_is_refused_honestly() -> None:
    facade = MCPToolFacade("srv", [_mcp("srv/read")])

    result = await facade.execute({"tool": "nope"}, None)

    assert result.success is False
    assert "nope" in (result.error or "")
    assert "read" in (result.error or "")


@pytest.mark.asyncio
async def test_arguments_must_be_an_object() -> None:
    facade = MCPToolFacade("srv", [_mcp("srv/read")])

    result = await facade.execute({"tool": "read", "arguments": "not-an-object"}, None)

    assert result.success is False
    assert "must be an object" in (result.error or "")


def test_the_per_call_tier_follows_the_selected_member() -> None:
    facade = MCPToolFacade(
        "srv", [_mcp("srv/read", risk_tier="safe"), _mcp("srv/write", risk_tier="ask")]
    )
    assert facade.risk_tier_for_args({"tool": "read"}) == "safe"
    assert facade.risk_tier_for_args({"tool": "write"}) == "ask"
    # An unknown member is refused anyway; until then the highest tier stands.
    assert facade.risk_tier_for_args({"tool": "unknown"}) == "ask"


def test_a_members_own_per_call_hook_is_used() -> None:
    class _Hooked:
        name = "srv/mail"
        risk_tier = "ask"

        def risk_tier_for_args(self, args: dict[str, Any]) -> str:
            return "safe" if args.get("mode") == "read" else "ask"

    facade = MCPToolFacade("srv", [_Hooked()])

    assert facade.risk_tier_for_args({"tool": "mail", "arguments": {"mode": "read"}}) == "safe"
    assert facade.risk_tier_for_args({"tool": "mail", "arguments": {}}) == "ask"


def test_a_broken_hook_keeps_the_inherited_tier() -> None:
    """A hook that raises must never WIDEN access — the static tier stands."""

    class _Broken:
        name = "srv/x"
        risk_tier = "block"

        def risk_tier_for_args(self, args: dict[str, Any]) -> str:
            raise RuntimeError("boom")

    facade = MCPToolFacade("srv", [_Broken()])

    assert facade.risk_tier_for_args({"tool": "x"}) == "block"


# ------------------------------------------------------------- the folding


def test_folding_takes_the_largest_group_in_registry_order() -> None:
    tools = {
        "run_shell": _FakeTool(name="run_shell"),
        "a/one": _mcp("a/one"),
        "b/one": _mcp("b/one"),
        "b/two": _mcp("b/two"),
        "b/three": _mcp("b/three"),
    }

    folded = _fold_largest_mcp_group(tools)

    assert folded is not None
    assert list(folded) == ["run_shell", "a/one", "b/_tools"]
    assert isinstance(folded["b/_tools"], MCPToolFacade)
    assert set(folded["b/_tools"].member_names) == {"one", "two", "three"}


def test_a_lone_server_tool_is_not_folded() -> None:
    tools = {"a/one": _mcp("a/one"), "run_shell": _FakeTool(name="run_shell")}
    assert _fold_largest_mcp_group(tools) is None


def test_a_real_underscore_tools_tool_keeps_that_server_unfolded() -> None:
    """A server that genuinely offers ``_tools`` must not be double-named."""
    tools = {
        "a/_tools": _mcp("a/_tools"),
        "a/one": _mcp("a/one"),
        "b/one": _mcp("b/one"),
        "b/two": _mcp("b/two"),
    }

    folded = _fold_largest_mcp_group(tools)

    assert folded is not None
    assert "a/_tools" in folded and "a/one" in folded  # a left untouched
    assert "b/_tools" in folded
    assert not any(isinstance(t, MCPToolFacade) and t.server == "a" for t in folded.values())


def test_folding_stops_as_soon_as_the_surface_fits() -> None:
    """Compression is a last resort: a server that already fits keeps its schemas."""
    tools: dict[str, Any] = {"run_shell": _FakeTool(name="run_shell", schema=_pad(1))}
    for i in range(6):
        tools[f"a/t{i}"] = _mcp(f"a/t{i}", schema=_pad(20))
    for i in range(6):
        tools[f"b/t{i}"] = _mcp(f"b/t{i}", schema=_pad(20))
    once = _fold_largest_mcp_group(tools)
    assert once is not None
    budget = sum(_tool_surface_tokens(n, t) for n, t in once.items())

    surface, groups = _fold_mcp_surface(
        tools, context_window=budget + 50, used_tokens=0, keep=(), max_tools=0
    )

    assert groups == 1
    assert sum(1 for t in surface.values() if getattr(t, "is_mcp_facade", False)) == 1
    assert "b/t0" in surface  # the second server is untouched


def test_folding_keeps_a_server_the_trim_would_have_emptied() -> None:
    tools: dict[str, Any] = {"run_shell": _FakeTool(name="run_shell", schema=_pad(2))}
    for i in range(92):
        tools[f"mcp/t{i}"] = _mcp(f"mcp/t{i}", schema=_pad(20))
    facade_only = {
        "run_shell": tools["run_shell"],
        "mcp/_tools": MCPToolFacade("mcp", [tools[f"mcp/t{i}"] for i in range(92)]),
    }
    budget = sum(_tool_surface_tokens(n, t) for n, t in facade_only.items())

    raw, dropped = _fit_tools_to_context_window(tools, context_window=budget, used_tokens=0)
    assert dropped and not any(n.startswith("mcp/") for n in raw)

    folded, groups = _fold_mcp_surface(
        tools, context_window=budget, used_tokens=0, keep=(), max_tools=0
    )

    assert groups == 1
    assert "mcp/_tools" in folded
    assert "run_shell" in folded
    assert len(folded["mcp/_tools"].member_names) == 92


def test_a_surface_that_fits_neither_way_keeps_the_old_trim() -> None:
    """Folding may only WIN capabilities — never reshuffle which are lost.

    When the request does not fit even fully folded, the caller keeps its usual
    trim of the ORIGINAL surface, so this feature cannot change the outcome of
    a turn that was already hopeless.
    """
    tools: dict[str, Any] = {"run_shell": _FakeTool(name="run_shell", schema=_pad(2))}
    for i in range(92):
        tools[f"mcp/t{i}"] = _mcp(f"mcp/t{i}", schema=_pad(20))

    folded, groups = _fold_mcp_surface(
        tools, context_window=10, used_tokens=5_000, keep=(), max_tools=0
    )

    assert groups == 0
    assert folded is tools


def test_the_manager_folds_before_it_hides() -> None:
    manager = BrainManager.__new__(BrainManager)  # bypass the heavy __init__
    manager._tools = {}
    manager._evidence_required_tool = None
    manager._skill_turn_match = None
    tools: dict[str, Any] = {"run_shell": _FakeTool(name="run_shell", schema=_pad(2))}
    for i in range(92):
        tools[f"mcp/t{i}"] = _mcp(f"mcp/t{i}", schema=_pad(20))
    facade_only = {
        "run_shell": tools["run_shell"],
        "mcp/_tools": MCPToolFacade("mcp", [tools[f"mcp/t{i}"] for i in range(92)]),
    }
    budget = sum(_tool_surface_tokens(n, t) for n, t in facade_only.items())

    class _Brain:
        name = "local"
        # A little slack: the fit adds what it estimates the prompt costs.
        context_window = budget + _CONTEXT_FIT_RESERVE_TOKENS + 200
        supports_vision = False

    fitted = manager._fit_tools_to_brain(tools, _Brain(), system_prompt="", history=None)

    assert "mcp/_tools" in fitted  # every server tool is still reachable
    assert "run_shell" in fitted  # and the built-in was never sacrificed
    assert not any(n.startswith("mcp/t") for n in fitted)
