"""Offline tests for the ``web_search`` tool."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest

from search_mcp.tools.web_search import web_search


def _hit(
    title: str,
    url: str,
    score: float | None = None,
    engine: str = "google",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "url": url,
        "content": f"snippet {title}",
        "engine": engine,
        "category": "general",
    }
    if score is not None:
        payload["score"] = score
    return payload


@pytest.mark.asyncio
async def test_web_search_returns_sorted_results(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
    make_search_payload: Callable[..., dict[str, Any]],
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        seen.update(dict(request.url.params))
        return json_response(
            make_search_payload(
                [
                    _hit("Second", "https://b.test/", score=0.2, engine="bing"),
                    _hit("First", "https://a.test", score=0.9, engine="google"),
                ],
                number=2,
            )
        )

    install_transport(handler)
    result = await web_search("hello world")

    assert result["ok"] is True
    payload = result["result"]
    assert payload["query"] == "hello world"
    assert payload["number_of_results"] == 2
    assert [item["title"] for item in payload["results"]] == ["First", "Second"]
    assert payload["engines_used"] == ["google", "bing"]
    assert seen["q"] == "hello world"
    assert seen["format"] == "json"
    assert seen["pageno"] == "1"
    json.dumps(result, allow_nan=False)


@pytest.mark.asyncio
async def test_web_search_truncates_to_max_results(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
    make_search_payload: Callable[..., dict[str, Any]],
) -> None:
    results = [_hit(f"R{i}", f"https://r{i}.test", score=1.0 - i / 10) for i in range(5)]
    install_transport(lambda request: json_response(make_search_payload(results)))

    result = await web_search("x", max_results=2)

    assert result["ok"] is True
    assert len(result["result"]["results"]) == 2


@pytest.mark.asyncio
async def test_web_search_keeps_order_without_scores(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
    make_search_payload: Callable[..., dict[str, Any]],
) -> None:
    results = [_hit("A", "https://a.test"), _hit("B", "https://b.test")]
    install_transport(lambda request: json_response(make_search_payload(results)))

    result = await web_search("x")

    assert [item["title"] for item in result["result"]["results"]] == ["A", "B"]
    assert all(item["score"] is None for item in result["result"]["results"])


@pytest.mark.asyncio
async def test_web_search_forwards_optional_parameters(
    install_transport: Callable[..., Any],
    json_response: Callable[..., httpx.Response],
    make_search_payload: Callable[..., dict[str, Any]],
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return json_response(make_search_payload([]))

    install_transport(handler)
    result = await web_search(
        "x",
        categories="news",
        engines="google,bing",
        time_range="week",
        pageno=3,
        language="en",
    )

    assert result["ok"] is True
    assert captured["categories"] == "news"
    assert captured["engines"] == "google,bing"
    assert captured["time_range"] == "week"
    assert captured["pageno"] == "3"
    assert captured["language"] == "en"


@pytest.mark.asyncio
async def test_web_search_rejects_bad_time_range(
    install_transport: Callable[..., Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await web_search("x", time_range="yesterday")

    assert result["ok"] is False
    assert "time_range" in result["error"]
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 51, "5"])
async def test_web_search_rejects_bad_max_results(
    install_transport: Callable[..., Any],
    value: Any,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": []})

    install_transport(handler)
    result = await web_search("x", max_results=value)

    assert result["ok"] is False
    assert "max_results" in result["error"]
    assert calls == 0


@pytest.mark.asyncio
async def test_web_search_retries_500_then_fails(
    install_transport: Callable[..., Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="upstream exploded")

    install_transport(handler)
    result = await web_search("x")

    assert result["ok"] is False
    assert "500" in result["error"]
    assert calls == 4  # initial attempt + 3 retries


@pytest.mark.asyncio
async def test_web_search_does_not_retry_4xx(
    install_transport: Callable[..., Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, text="bad request")

    install_transport(handler)
    result = await web_search("x")

    assert result["ok"] is False
    assert "400" in result["error"]
    assert calls == 1
