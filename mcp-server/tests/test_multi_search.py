"""Offline tests for the ``multi_search`` tool."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import httpx
import pytest

from search_mcp.tools.multi_search import multi_search

RESULTS: dict[str, list[dict[str, Any]]] = {
    "alpha": [
        {
            "title": "Alpha shared",
            "url": "https://Example.com/page/?utm_source=x&id=1",
            "content": "a",
            "engine": "google",
            "score": 0.5,
            "category": "general",
        },
        {
            "title": "Alpha unique",
            "url": "https://unique.test/a",
            "content": "b",
            "engine": "google",
            "score": 0.3,
            "category": "general",
        },
    ],
    "beta": [
        {
            "title": "Beta shared",
            "url": "https://example.com/page?id=1",
            "content": "c",
            "engine": "bing",
            "score": 0.9,
            "category": "general",
        },
        {
            "title": "Beta unique",
            "url": "https://unique.test/b",
            "content": "d",
            "engine": "bing",
            "score": 0.4,
            "category": "general",
        },
    ],
}


def _handler(request: httpx.Request) -> httpx.Response:
    query = request.url.params["q"]
    return httpx.Response(
        200,
        json={"number_of_results": len(RESULTS.get(query, [])), "results": RESULTS.get(query, [])},
    )


@pytest.mark.asyncio
async def test_multi_search_dedupes_and_merges_engines(
    install_transport: Callable[..., Any],
) -> None:
    install_transport(_handler)
    result = await multi_search(["alpha", "beta"], max_results=5, concurrency=2)

    assert result["ok"] is True
    payload = result["result"]
    assert set(payload["queries"]) == {"alpha", "beta"}
    assert len(payload["queries"]["alpha"]) == 2
    assert payload["errors"] == {}
    assert len(payload["merged"]) == 3

    shared = next(item for item in payload["merged"] if "example.com" in item["url"])
    assert shared["score"] == 0.9
    assert shared["title"] == "Beta shared"
    assert set(shared["engines"]) == {"google", "bing"}


@pytest.mark.asyncio
async def test_multi_search_without_dedupe(
    install_transport: Callable[..., Any],
) -> None:
    install_transport(_handler)
    result = await multi_search(["alpha", "beta"], dedupe=False)

    assert result["ok"] is True
    assert len(result["result"]["merged"]) == 4


@pytest.mark.asyncio
async def test_multi_search_respects_concurrency(
    install_transport: Callable[..., Any],
) -> None:
    active = 0
    max_active = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await multi_search(["q1", "q2", "q3", "q4"], concurrency=2)

    assert result["ok"] is True
    assert max_active == 2


@pytest.mark.asyncio
async def test_multi_search_collects_per_query_errors(
    install_transport: Callable[..., Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["q"] == "bad":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await multi_search(["good", "bad"])

    assert result["ok"] is True
    payload = result["result"]
    assert payload["queries"]["good"] == []
    assert "bad" in payload["errors"]
    assert "500" in payload["errors"]["bad"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"queries": []},
        {"queries": [f"q{i}" for i in range(11)]},
        {"queries": ["x"], "concurrency": 0},
        {"queries": ["x"], "concurrency": 9},
        {"queries": ["x"], "max_results": 0},
    ],
)
async def test_multi_search_validation(
    install_transport: Callable[..., Any],
    kwargs: dict[str, Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await multi_search(**kwargs)

    assert result["ok"] is False
    assert calls == 0


@pytest.mark.asyncio
async def test_multi_search_rejects_non_list_queries(
    install_transport: Callable[..., Any],
) -> None:
    install_transport(lambda request: httpx.Response(200, json={"results": []}))
    result = await multi_search("single string")  # type: ignore[arg-type]
    assert result["ok"] is False
