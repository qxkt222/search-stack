"""Offline tests for the ``search_compare`` tool."""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from search_mcp.tools.search_compare import search_compare


@pytest.mark.asyncio
async def test_search_compare_reports_per_engine_results_and_errors(
    install_transport: Callable[..., Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        engine = request.url.params["engines"]
        if engine == "bing":
            return httpx.Response(500, text="engine down")
        return httpx.Response(
            200,
            json={
                "number_of_results": 1,
                "results": [
                    {
                        "title": f"{engine} hit",
                        "url": f"https://{engine}.test/1",
                        "content": "snippet",
                        "engine": engine,
                        "score": 1.0,
                        "category": "general",
                    }
                ],
            },
        )

    install_transport(handler)
    result = await search_compare("python", ["google", "bing"])

    assert result["ok"] is True
    payload = result["result"]
    assert payload["query"] == "python"
    assert [item["title"] for item in payload["engines"]["google"]] == ["google hit"]
    assert payload["engines"]["bing"] == []
    assert "bing" in payload["errors"]
    assert "500" in payload["errors"]["bing"]
    assert "google" not in payload["errors"]


@pytest.mark.asyncio
async def test_search_compare_passes_max_results(
    install_transport: Callable[..., Any],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": f"r{i}",
                        "url": f"https://e.test/{i}",
                        "content": "",
                        "engine": request.url.params["engines"],
                        "score": 1.0 - i / 10,
                        "category": "general",
                    }
                    for i in range(6)
                ]
            },
        )

    install_transport(handler)
    result = await search_compare("q", ["google"], max_results=2)

    assert result["ok"] is True
    assert len(result["result"]["engines"]["google"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engines",
    [[], [f"e{i}" for i in range(9)], "google"],
)
async def test_search_compare_validates_engines(
    install_transport: Callable[..., Any],
    engines: Any,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await search_compare("q", engines)

    assert result["ok"] is False
    assert "engines" in result["error"]
    assert calls == 0
