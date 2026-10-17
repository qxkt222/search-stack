"""Shared offline test fixtures."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from search_mcp import client, core


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Deterministic environment, no retry sleeps and an empty cache per test."""

    monkeypatch.setenv("SEARXNG_URL", "http://localhost:8888")
    monkeypatch.delenv("SEARCH_MCP_PROXY", raising=False)
    monkeypatch.delenv("SEARCH_MCP_TIMEOUT", raising=False)
    monkeypatch.delenv("SEARCH_MCP_CACHE_TTL", raising=False)
    monkeypatch.delenv("SEARCH_MCP_FETCH_CACHE_TTL", raising=False)
    monkeypatch.setattr(core, "RETRY_DELAYS", (0.0, 0.0, 0.0))

    core.CACHE.clear()
    client.set_transport(None)
    yield
    client.reset_clients()
    client.set_transport(None)
    core.CACHE.clear()


@pytest.fixture
def install_transport() -> Callable[[Callable[[httpx.Request], httpx.Response]], None]:
    """Install an ``httpx.MockTransport`` handler for the current test."""

    def _install(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> httpx.MockTransport:
        transport = httpx.MockTransport(handler)
        client.set_transport(transport)
        return transport

    return _install


@pytest.fixture
def json_response() -> Callable[..., httpx.Response]:
    def _response(payload: Any, status: int = 200) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return _response


def search_payload(results: list[dict[str, Any]], number: int | None = None) -> dict[str, Any]:
    return {
        "number_of_results": len(results) if number is None else number,
        "results": results,
    }


@pytest.fixture
def make_search_payload() -> Callable[..., dict[str, Any]]:
    return search_payload
