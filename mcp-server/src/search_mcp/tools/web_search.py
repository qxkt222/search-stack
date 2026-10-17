"""``web_search`` tool."""

from __future__ import annotations

from typing import Any

from .. import client, core


async def web_search(
    query: str,
    max_results: int = 10,
    categories: str | None = None,
    engines: str | None = None,
    time_range: str | None = None,
    pageno: int = 1,
    language: str | None = None,
) -> dict[str, Any]:
    """Search the web with SearXNG and return normalised results.

    Args:
        query: Search terms.
        max_results: Maximum number of results (1-50).
        categories: Comma-separated SearXNG categories.
        engines: Comma-separated SearXNG engine names.
        time_range: One of day, week, month or year.
        pageno: Result page number (1-10).
        language: Language code such as "en" or "zh-CN".

    Returns:
        ``{"ok": true, "result": {query, number_of_results, results, engines_used}}``
        or ``{"ok": false, "error": "..."}``.
    """

    try:
        query = core.check_text(query, "query")
        core.check_int(max_results, "max_results", 1, 50)
        core.check_int(pageno, "pageno", 1, 10)
        time_range = core.check_time_range(time_range)
        categories = core.check_optional_text(categories, "categories")
        engines = core.check_optional_text(engines, "engines")
        language = core.check_optional_text(language, "language")

        result = await client.search(
            query,
            max_results=max_results,
            categories=categories,
            engines=engines,
            time_range=time_range,
            pageno=pageno,
            language=language,
        )
        return core.ok(result)
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def register(mcp: Any) -> None:
    mcp.tool()(web_search)
