"""Offline tests for health, cache and configuration tools."""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from search_mcp import client
from search_mcp.tools.health import (
    cache_clear,
    cache_stats,
    config_info,
    health_check,
)


def _search_body() -> dict[str, Any]:
    return {
        "number_of_results": 1,
        "results": [
            {
                "title": "probe",
                "url": "https://probe.test/",
                "content": "probe",
                "engine": "google",
                "score": 1.0,
                "category": "general",
            }
        ],
    }


@pytest.mark.asyncio
async def test_health_check_success(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, text="OK")
        return json_response(_search_body())

    install_transport(handler)
    result = await health_check()

    assert result["ok"] is True
    payload = result["result"]
    assert payload["ok"] is True
    assert payload["searxng"] == {
        "url": "http://localhost:8888",
        "ok": True,
        "status": 200,
    }
    assert payload["search"]["ok"] is True
    assert payload["search"]["results_count"] == 1
    assert payload["search"]["number_of_results"] == 1
    assert payload["proxy"] == {"configured": False, "masked": None}
    assert payload["cache"]["entries"] == 1


@pytest.mark.asyncio
async def test_health_check_healthz_failure(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
) -> None:
    health_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal health_calls
        if request.url.path == "/healthz":
            health_calls += 1
            return httpx.Response(503, text="unavailable")
        return json_response(_search_body())

    install_transport(handler)
    result = await health_check()

    assert result["ok"] is True
    payload = result["result"]
    assert payload["ok"] is False
    assert payload["searxng"]["ok"] is False
    assert payload["searxng"]["status"] == 503
    assert payload["search"]["ok"] is True
    assert health_calls == 4


@pytest.mark.asyncio
async def test_health_check_search_failure(
    install_transport: Callable[..., Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, text="OK")
        return httpx.Response(500, text="search down")

    install_transport(handler)
    result = await health_check()

    assert result["ok"] is True
    payload = result["result"]
    assert payload["ok"] is False
    assert payload["searxng"]["ok"] is True
    assert payload["search"]["ok"] is False
    assert "500" in payload["search"]["error"]


@pytest.mark.asyncio
async def test_cache_stats_and_clear(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
) -> None:
    install_transport(lambda request: json_response(_search_body()))

    await client.search("cached query")
    stats = cache_stats()
    assert stats["ok"] is True
    assert stats["result"]["entries"] == 1
    assert stats["result"]["misses"] == 1
    assert stats["result"]["hits"] == 0

    cleared = cache_clear()
    assert cleared["ok"] is True
    assert cleared["result"]["cleared"] == 1
    assert cleared["result"]["entries"] == 0
    assert cache_stats()["result"] == {"entries": 0, "hits": 0, "misses": 0}


def test_cache_stats_envelope_shape() -> None:
    result = cache_stats()
    assert set(result) == {"ok", "result"}
    assert set(result["result"]) == {"entries", "hits", "misses"}


def test_config_info_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = config_info()
    assert result["ok"] is True
    info = result["result"]
    assert info["searxng_url"] == "http://localhost:8888"
    assert info["timeout"] == 20.0
    assert info["cache_ttl"] == {"search": 300.0, "fetch": 3600.0}
    assert info["proxy"] == {"configured": False, "masked": None}


def test_config_info_masks_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEARCH_MCP_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("SEARCH_MCP_TIMEOUT", "7.5")
    monkeypatch.setenv("SEARCH_MCP_CACHE_TTL", "42")

    result = config_info()
    info = result["result"]
    assert info["timeout"] == 7.5
    assert info["cache_ttl"]["search"] == 42.0
    assert info["proxy"]["configured"] is True
    assert "3128" not in info["proxy"]["masked"]
    assert "proxy.example" in info["proxy"]["masked"]
