"""Offline tests for the ``web_fetch`` tool."""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from search_mcp import core
from search_mcp.tools.health import cache_stats
from search_mcp.tools.web_fetch import web_fetch

ARTICLE = """
<!doctype html>
<html>
  <head><title>Test Page</title></head>
  <body>
    <nav><a href="/home">Home</a></nav>
    <article>
      <h1>Article heading</h1>
      <p>This is the first paragraph with enough text to be extracted properly
      by the readability algorithm used in production.</p>
      <p>The second paragraph adds more body content so the extractor has a
      reasonable amount of text to work with.</p>
    </article>
    <footer>footer noise</footer>
  </body>
</html>
"""


def _html_with_links(count: int) -> str:
    anchors = "".join(
        f'<a href="/relative/{i}">link {i}</a>'
        if i % 2
        else f'<a href="https://other.test/page/{i}">link {i}</a>'
        for i in range(count)
    )
    anchors += '<a href="mailto:x@example.com">mail</a>'
    anchors += '<a href="#fragment">fragment</a>'
    return (
        "<html><head><title>Links</title></head><body><article>"
        f"<p>Body text with many links.</p>{anchors}</article></body></html>"
    )


def _html_response(html: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        text=html,
        headers={"content-type": "text/html; charset=utf-8"},
    )


@pytest.mark.asyncio
async def test_web_fetch_extracts_text(
    install_transport: Callable[..., Any],
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _html_response(ARTICLE)

    install_transport(handler)
    result = await web_fetch("https://site.test/article")

    assert result["ok"] is True
    page = result["result"]
    assert page["url"] == "https://site.test/article"
    assert page["final_url"] == "https://site.test/article"
    assert page["status"] == 200
    assert page["title"] == "Test Page"
    assert "first paragraph" in page["text"]
    assert page["chars"] == len(page["text"])
    assert page["truncated"] is False
    assert page["excerpt"]
    assert "links" not in page
    assert seen == ["https://site.test/article"]


@pytest.mark.asyncio
async def test_web_fetch_truncates_text(
    install_transport: Callable[..., Any],
) -> None:
    paragraphs = "".join(
        f"<p>Paragraph {i}: " + ("long unique body sentence " * 10) + f" marker{i}.</p>"
        for i in range(30)
    )
    html = f"<html><head><title>Long</title></head><body><article>{paragraphs}</article></body></html>"
    install_transport(lambda request: _html_response(html))

    result = await web_fetch("https://site.test/long", max_chars=1000)

    assert result["ok"] is True
    page = result["result"]
    assert page["truncated"] is True
    assert page["chars"] == 1000
    assert len(page["text"]) == 1000


@pytest.mark.asyncio
async def test_web_fetch_404_is_not_retried(
    install_transport: Callable[..., Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, text="missing")

    install_transport(handler)
    result = await web_fetch("https://site.test/missing")

    assert result["ok"] is False
    assert result["status"] == 404
    assert "404" in result["error"]
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    ["", "not-a-url", "ftp://site.test/file", "https://"],
)
async def test_web_fetch_rejects_invalid_url(
    install_transport: Callable[..., Any],
    url: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _html_response(ARTICLE)

    install_transport(handler)
    result = await web_fetch(url)

    assert result["ok"] is False
    assert "url" in result["error"].lower()
    assert calls == 0


@pytest.mark.asyncio
async def test_web_fetch_rejects_bad_max_chars(
    install_transport: Callable[..., Any],
) -> None:
    install_transport(lambda request: _html_response(ARTICLE))
    result = await web_fetch("https://site.test/a", max_chars=999)
    assert result["ok"] is False
    assert "max_chars" in result["error"]


@pytest.mark.asyncio
async def test_web_fetch_include_links(
    install_transport: Callable[..., Any],
) -> None:
    install_transport(lambda request: _html_response(_html_with_links(60)))
    result = await web_fetch("https://site.test/links", include_links=True)

    assert result["ok"] is True
    links = result["result"]["links"]
    assert len(links) == 50
    assert all(link.startswith("http") for link in links)
    assert "https://site.test/relative/1" in links
    assert not any("mailto:" in link or "#fragment" in link for link in links)


@pytest.mark.asyncio
async def test_web_fetch_cache_hits(
    install_transport: Callable[..., Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _html_response(ARTICLE)

    install_transport(handler)
    await web_fetch("https://site.test/page?utm_source=newsletter")
    second = await web_fetch("https://SITE.test/page#section")

    assert second["ok"] is True
    assert calls == 1
    stats = cache_stats()["result"]
    assert stats["entries"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert core.CACHE.stats()["entries"] == 1
