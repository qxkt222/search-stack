"""``search_and_fetch`` tool: search, then fetch the top hits concurrently."""

from __future__ import annotations

import asyncio
from typing import Any

from .. import client, core
from .web_fetch import fetch_page


async def search_and_fetch(
    query: str,
    top_n: int = 3,
    max_chars: int = 8000,
    categories: str | None = None,
    engines: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    pageno: int = 1,
) -> dict[str, Any]:
    """Search the web and return the readable text of the top results.

    Args:
        query: Search terms.
        top_n: Number of results to fetch (1-10).
        max_chars: Maximum characters of text per page (1000-200000).
        categories: Comma-separated SearXNG categories.
        engines: Comma-separated SearXNG engine names.
        time_range: One of day, week, month or year.
        language: Language code.
        pageno: SearXNG result page (1-10).

    Returns:
        ``{"ok": true, "result": {query, items, errors}}`` where each item has
        title, url, snippet, engine, content, chars and optionally error.
    """

    try:
        query = core.check_text(query, "query")
        core.check_int(top_n, "top_n", 1, 10)
        core.check_int(max_chars, "max_chars", 1000, 200000)
        core.check_int(pageno, "pageno", 1, 10)
        time_range = core.check_time_range(time_range)
        categories = core.check_optional_text(categories, "categories")
        engines = core.check_optional_text(engines, "engines")
        language = core.check_optional_text(language, "language")

        search_result = await client.search(
            query,
            max_results=top_n,
            categories=categories,
            engines=engines,
            time_range=time_range,
            pageno=pageno,
            language=language,
        )
        results = search_result["results"][:top_n]
        semaphore = asyncio.Semaphore(max(1, len(results)))

        async def fetch_one(hit: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, str] | None]:
            async with semaphore:
                fetched = await fetch_page(
                    hit["url"], max_chars=max_chars, include_links=False
                )
            item: dict[str, Any] = {
                "title": hit.get("title") or "",
                "url": hit.get("url") or "",
                "snippet": hit.get("content") or "",
                "engine": hit.get("engine") or "",
                "content": "",
                "chars": 0,
            }
            if fetched.get("ok"):
                page = fetched["result"]
                if not item["title"]:
                    item["title"] = page.get("title") or ""
                item["content"] = page.get("text") or ""
                item["chars"] = int(page.get("chars") or 0)
                return item, None
            message = str(fetched.get("error") or "fetch failed")
            item["error"] = message
            return item, (item["url"], message)

        pairs = await asyncio.gather(*(fetch_one(hit) for hit in results))
        items = [item for item, _ in pairs]
        errors: dict[str, str] = {}
        for _, failure in pairs:
            if failure:
                error_url, message = failure
                errors[error_url] = message
        return core.ok({"query": query, "items": items, "errors": errors})
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def register(mcp: Any) -> None:
    mcp.tool()(search_and_fetch)
