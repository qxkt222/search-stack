"""Offline tests for the ``search_and_fetch`` tool."""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from search_mcp.tools.search_and_fetch import search_and_fetch

ARTICLE = (
    "<html><head><title>Page</title></head><body><article>"
    "<p>Readable page body with a reasonable amount of text for extraction.</p>"
    "</article></body></html>"
)


def _html_response(html: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, text=html, headers={"content-type": "text/html; charset=utf-8"}
    )


@pytest.mark.asyncio
async def test_single_fetch_failure_does_not_break_others(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
) -> None:
    page_calls: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return json_response(
                {
                    "number_of_results": 2,
                    "results": [
                        {
                            "title": "Good",
                            "url": "https://good.test/page",
                            "content": "good snippet",
                            "engine": "google",
                            "score": 0.9,
                        },
                        {
                            "title": "Bad",
                            "url": "https://bad.test/page",
                            "content": "bad snippet",
                            "engine": "bing",
                            "score": 0.5,
                        },
                    ],
                }
            )
        page_calls[request.url.path] = page_calls.get(request.url.path, 0) + 1
        if request.url.host == "bad.test":
            return httpx.Response(500, text="broken")
        return _html_response(ARTICLE)

    install_transport(handler)
    result = await search_and_fetch("query", top_n=3)

    assert result["ok"] is True
    payload = result["result"]
    assert payload["query"] == "query"
    assert len(payload["items"]) == 2

    good = next(item for item in payload["items"] if item["url"].startswith("https://good"))
    bad = next(item for item in payload["items"] if item["url"].startswith("https://bad"))

    assert good["content"]
    assert good["chars"] > 0
    assert good["snippet"] == "good snippet"
    assert "error" not in good

    assert bad["content"] == ""
    assert bad["chars"] == 0
    assert "error" in bad

    assert "https://bad.test/page" in payload["errors"]
    assert "500" in payload["errors"]["https://bad.test/page"]
    assert page_calls["/page"] == 5  # one good + four failed attempts on bad


@pytest.mark.asyncio
async def test_top_n_limits_fetched_pages(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
) -> None:
    page_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_calls
        if request.url.path == "/search":
            return json_response(
                {
                    "results": [
                        {"title": f"R{i}", "url": f"https://r{i}.test/page", "content": ""}
                        for i in range(4)
                    ]
                }
            )
        page_calls += 1
        return _html_response(ARTICLE)

    install_transport(handler)
    result = await search_and_fetch("q", top_n=1)

    assert result["ok"] is True
    assert len(result["result"]["items"]) == 1
    assert page_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 11])
async def test_invalid_top_n(
    install_transport: Callable[..., Any],
    value: int,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return json_response_stub()

    def json_response_stub() -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await search_and_fetch("q", top_n=value)

    assert result["ok"] is False
    assert "top_n" in result["error"]
    assert calls == 0
