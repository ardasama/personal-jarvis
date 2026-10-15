"""Unknown-name errors from manage-mcp-server must be actionable.

Forensic 2026-07-13 18:33: "reconnect the GitHub MCP" failed with a bare
"no MCP server named 'github'" — GitHub was a marketplace plugin, not an
mcp.json server — and the spoken outcome gave the user nothing to correct.
"""

from __future__ import annotations

import pytest

from jarvis.plugins.tool.manage_mcp_server import ManageMcpServerTool


class _FakeMcpState:
    def __init__(self, servers: dict | None = None) -> None:
        self._servers = servers or {}

    def load_config(self) -> dict:
        return {"mcpServers": dict(self._servers)}

    def get_server_entry(self, name: str) -> dict | None:
        return self._servers.get(name)

    def remove_server(self, name: str) -> bool:
        return self._servers.pop(name, None) is not None


@pytest.mark.asyncio
async def test_toggle_unknown_name_lists_configured_servers() -> None:
    state = _FakeMcpState({"notebooklm": {"enabled": True}, "blender": {}})
    result = await ManageMcpServerTool()._toggle(
        state, "github", enabled=True, reason="test"
    )
    assert result.success is False
    assert "github" in result.error
    assert "notebooklm" in result.error
    assert "blender" in result.error
    assert "plugin" in result.error.lower()


@pytest.mark.asyncio
async def test_remove_unknown_name_lists_configured_servers() -> None:
    state = _FakeMcpState({"notebooklm": {"enabled": True}})
    result = await ManageMcpServerTool()._remove(state, "github", "test")
    assert result.success is False
    assert "notebooklm" in result.error


@pytest.mark.asyncio
async def test_unknown_name_error_survives_a_broken_state() -> None:
    class _BrokenState:
        def load_config(self):
            raise RuntimeError("boom")

        def get_server_entry(self, _name):
            return None

    result = await ManageMcpServerTool()._toggle(
        _BrokenState(), "github", enabled=True, reason="test"
    )
    assert result.success is False
    assert "github" in result.error


# ---------------------------------------------------------------------------
# Live enable/disable reporting (audit 2026-08-08 §3 item 1)
# ---------------------------------------------------------------------------
# The tool decided "did the enable take effect live?" by calling
# ``registry.active_names()`` — a method ``MCPRegistry`` did not have. The
# resulting AttributeError was caught by a bare ``except``, so ``applied_live``
# stayed False and every enable told the user a restart was required even when
# the server had actually started.


class _ToggleState:
    """mcp.json state double that records the enable/disable write."""

    def __init__(self) -> None:
        self.enabled_calls: list[tuple[str, bool]] = []

    def get_server_entry(self, name: str) -> dict | None:
        return {"enabled": False} if name == "filesystem" else None

    def set_enabled(self, name: str, enabled: bool) -> None:
        self.enabled_calls.append((name, enabled))


class _ToggleRegistry:
    """Registry double: starts a server and reports it live (or not)."""

    def __init__(self, *, reports_active: bool = True) -> None:
        self._reports_active = reports_active
        self.started: list[list[str]] = []
        self.reloads = 0

    def load_from_mcp_json(self) -> None:
        self.reloads += 1

    async def start_enabled(self, names: list[str]) -> None:
        self.started.append(list(names))

    def active_names(self) -> list[str]:
        return ["filesystem"] if self._reports_active else []


def _wire_registry(monkeypatch, registry) -> None:
    monkeypatch.setattr(
        ManageMcpServerTool, "_registry", staticmethod(lambda: registry)
    )


@pytest.mark.asyncio
async def test_enable_reports_applied_live_when_registry_confirms(monkeypatch) -> None:
    state = _ToggleState()
    _wire_registry(monkeypatch, _ToggleRegistry(reports_active=True))

    result = await ManageMcpServerTool()._toggle(
        state, "filesystem", enabled=True, reason="test"
    )

    assert result.success is True
    assert result.output["applied_live"] is True
    assert result.output["requires_restart"] is False
    assert state.enabled_calls == [("filesystem", True)]


@pytest.mark.asyncio
async def test_enable_asks_for_restart_when_registry_does_not_confirm(
    monkeypatch,
) -> None:
    state = _ToggleState()
    registry = _ToggleRegistry(reports_active=False)
    _wire_registry(monkeypatch, registry)

    result = await ManageMcpServerTool()._toggle(
        state, "filesystem", enabled=True, reason="test"
    )

    assert result.success is True
    assert result.output["applied_live"] is False
    assert result.output["requires_restart"] is True
    assert registry.started == [["filesystem"]]


@pytest.mark.asyncio
async def test_enable_survives_a_registry_without_active_names(monkeypatch) -> None:
    """An introspection failure must degrade honestly, never crash the tool."""

    class _NoIntrospection(_ToggleRegistry):
        def active_names(self):
            raise AttributeError("'MCPRegistry' object has no attribute 'active_names'")

    state = _ToggleState()
    _wire_registry(monkeypatch, _NoIntrospection())

    result = await ManageMcpServerTool()._toggle(
        state, "filesystem", enabled=True, reason="test"
    )

    assert result.success is True
    assert result.output["applied_live"] is False
    assert result.output["requires_restart"] is True


def test_is_running_assumes_running_when_registry_cannot_answer(monkeypatch) -> None:
    """A registry that raises must not be read as "the drop already happened"."""

    class _Broken(_ToggleRegistry):
        def active_names(self):
            raise RuntimeError("registry wedged")

    _wire_registry(monkeypatch, _Broken())
    assert ManageMcpServerTool._is_running("filesystem") is True


def test_is_running_is_false_without_a_registry(monkeypatch) -> None:
    _wire_registry(monkeypatch, None)
    assert ManageMcpServerTool._is_running("filesystem") is False

