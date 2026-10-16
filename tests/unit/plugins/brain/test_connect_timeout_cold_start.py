"""A local server that is still loading its model must not cost the turn.

Live 2026-10-15 23:05:24: ``Brain ollama(qwen3.5:4b) fehlgeschlagen: Request
timed out.`` — two seconds after the tool-surface log, the (single-provider)
chain exhausted, and the user heard "provider unreachable — check the
network". Probe 2026-10-16: that exact text is ``openai.APITimeoutError``
raised from ``httpx.ConnectTimeout`` (the local brains' 2 s connect budget),
while ``http://127.0.0.1:11434/api/tags`` answered in 113 ms with ``qwen3.5:4b``
on the server. The server was up and merely cold.

Fix under test: ONE retry with a cold-start connect budget — local endpoints
only, so a cloud chain keeps fast-failing and moving on (AP-22).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from jarvis.plugins.brain._openai_base import (
    _COLD_START_CONNECT_TIMEOUT_S,
    _create_with_token_param_retry,
    _is_connect_timeout,
    _is_local_endpoint,
    _local_endpoint_cold_start_timeout,
)

#: The local brains' own client timeout (ollama / local-openai).
_LOCAL_TIMEOUT = httpx.Timeout(connect=2.0, read=120.0, write=30.0, pool=30.0)


def _sdk_connect_timeout() -> BaseException:
    """The SDK's real shape for a connect that never happened.

    Byte-identical to the live failure: ``APITimeoutError("Request timed out.")``
    caused by ``httpx.ConnectTimeout`` (probe-verified 2026-10-16).
    """
    exc = openai.APITimeoutError(
        request=httpx.Request("POST", "http://127.0.0.1:11434/v1/chat/completions")
    )
    exc.__cause__ = httpx.ConnectTimeout("connect timed out")
    return exc


class _FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(
        self, *, base_url: str, timeout: httpx.Timeout, outcomes: list[Any]
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.chat = SimpleNamespace(completions=_FakeCompletions(outcomes))


# ------------------------------------------------------- reading the failure


def test_the_live_failure_is_recognised_as_a_connect_timeout() -> None:
    assert _is_connect_timeout(_sdk_connect_timeout()) is True


def test_a_generation_timeout_is_not_a_connect_timeout() -> None:
    """A read timeout (the model answered too slowly) must not be retried."""
    exc = openai.APITimeoutError(request=httpx.Request("POST", "http://x/v1"))
    assert _is_connect_timeout(exc) is False
    assert _is_connect_timeout(RuntimeError("boom")) is False


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]:11434/v1",
        "http://192.168.1.9:8080/v1",
        "http://10.0.0.5:1234/v1",
        "http://host.docker.internal:11434/v1",
    ],
)
def test_local_endpoints_qualify(base_url: str) -> None:
    assert _is_local_endpoint(base_url) is True


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "https://openrouter.ai/api/v1",
        "https://api.x.ai/v1",
        "https://8.8.8.8/v1",
        "not a url",
        "",
    ],
)
def test_cloud_endpoints_do_not_qualify(base_url: str) -> None:
    assert _is_local_endpoint(base_url) is False


# ------------------------------------------------------------ the budget


def test_cold_start_budget_widens_the_connect_window_only() -> None:
    client = _FakeClient(
        base_url="http://127.0.0.1:11434/v1", timeout=_LOCAL_TIMEOUT, outcomes=[]
    )
    widened = _local_endpoint_cold_start_timeout(client)
    assert widened is not None
    assert widened.connect == _COLD_START_CONNECT_TIMEOUT_S
    assert widened.read == _LOCAL_TIMEOUT.read
    assert widened.write == _LOCAL_TIMEOUT.write


def test_no_cold_start_budget_for_a_cloud_endpoint() -> None:
    client = _FakeClient(
        base_url="https://api.openai.com/v1", timeout=_LOCAL_TIMEOUT, outcomes=[]
    )
    assert _local_endpoint_cold_start_timeout(client) is None


def test_an_already_wide_connect_budget_is_not_widened_again() -> None:
    client = _FakeClient(
        base_url="http://127.0.0.1:11434/v1",
        timeout=httpx.Timeout(connect=60.0, read=120.0, write=30.0, pool=30.0),
        outcomes=[],
    )
    assert _local_endpoint_cold_start_timeout(client) is None


# --------------------------------------------------------------- the retry


async def test_a_local_connect_timeout_retries_once_with_the_cold_budget() -> None:
    client = _FakeClient(
        base_url="http://127.0.0.1:11434/v1",
        timeout=_LOCAL_TIMEOUT,
        outcomes=[_sdk_connect_timeout(), "STREAM"],
    )

    result = await _create_with_token_param_retry(
        client, {"model": "qwen3.5:4b", "messages": [], "stream": True}
    )

    assert result == "STREAM"
    calls = client.chat.completions.calls
    assert len(calls) == 2
    # The first attempt keeps the fast-fail budget…
    assert "timeout" not in calls[0]
    # …the single retry carries the cold-start one, and nothing wider.
    retry_timeout = calls[1]["timeout"]
    assert retry_timeout.connect == _COLD_START_CONNECT_TIMEOUT_S
    assert retry_timeout.read == _LOCAL_TIMEOUT.read


async def test_a_cloud_connect_timeout_is_never_retried() -> None:
    client = _FakeClient(
        base_url="https://api.openai.com/v1",
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0),
        outcomes=[_sdk_connect_timeout()],
    )

    with pytest.raises(openai.APITimeoutError):
        await _create_with_token_param_retry(
            client, {"model": "gpt-5.5", "messages": [], "stream": True}
        )

    assert len(client.chat.completions.calls) == 1


async def test_a_non_timeout_failure_is_never_retried() -> None:
    client = _FakeClient(
        base_url="http://127.0.0.1:11434/v1",
        timeout=_LOCAL_TIMEOUT,
        outcomes=[RuntimeError("connection refused")],
    )

    with pytest.raises(RuntimeError):
        await _create_with_token_param_retry(
            client, {"model": "qwen3.5:4b", "messages": [], "stream": True}
        )

    assert len(client.chat.completions.calls) == 1


async def test_the_retry_happens_at_most_once() -> None:
    """Two connect timeouts in a row end the attempt honestly."""
    client = _FakeClient(
        base_url="http://127.0.0.1:11434/v1",
        timeout=_LOCAL_TIMEOUT,
        outcomes=[_sdk_connect_timeout(), _sdk_connect_timeout()],
    )

    with pytest.raises(openai.APITimeoutError):
        await _create_with_token_param_retry(
            client, {"model": "qwen3.5:4b", "messages": [], "stream": True}
        )

    assert len(client.chat.completions.calls) == 2
