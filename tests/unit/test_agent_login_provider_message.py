"""Keep provider-specific account login guidance correct and non-misleading."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from jarvis.ui.web import agent_accounts_routes


@pytest.mark.parametrize(
    ("platform", "expected", "not_expected"),
    [
        ("codex", "ChatGPT sign-in", "claude.com"),
        ("claude", "claude.com", "ChatGPT sign-in"),
        ("gemini", "finish it in the window", "claude.com"),
    ],
)
def test_cli_login_message_uses_matching_provider(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    expected: str,
    not_expected: str,
) -> None:
    account = SimpleNamespace(id="test", label="QA account", platform=platform)
    monkeypatch.setattr(agent_accounts_routes.agent_accounts, "resolve", lambda _: account)
    monkeypatch.setattr(agent_accounts_routes.agent_accounts, "start_login", lambda _: None)
    response = asyncio.run(agent_accounts_routes.login("test"))
    assert response["ok"] is True
    assert expected in response["message"]
    assert not_expected not in response["message"]