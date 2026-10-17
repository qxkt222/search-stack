"""``search_compare`` tool: compare per-engine result sets for one query."""

from __future__ import annotations

import asyncio
from typing import Any

from .. import client, core


async def search_compare(
    query: str,
    engines: list[str],
    max_results: int = 5,
    categories: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    pageno: int = 1,
) -> dict[str, Any]:
    """Run one query against each engine separately.

    Args:
        query: Search terms.
        engines: 1-8 SearXNG engine names (for example ["google", "bing"]).
        max_results: Maximum results per engine (1-50).
        categories: Comma-separated SearXNG categories.
        time_range: One of day, week, month or year.
        language: Language code.
        pageno: SearXNG result page (1-10).

    Returns:
        ``{"ok": true, "result": {query, engines: {name: results},
        errors: {name: message}}}``.
    """

    try:
        query = core.check_text(query, "query")
        engines = core.check_string_list(engines, "engines", 1, 8)
        core.check_int(max_results, "max_results", 1, 50)
        core.check_int(pageno, "pageno", 1, 10)
        time_range = core.check_time_range(time_range)
        categories = core.check_optional_text(categories, "categories")
        language = core.check_optional_text(language, "language")

        semaphore = asyncio.Semaphore(min(8, len(engines)))

        async def run_one(engine: str) -> tuple[str, list[dict[str, Any]], str | None]:
            async with semaphore:
                try:
                    result = await client.search(
                        query,
                        max_results=max_results,
                        categories=categories,
                        engines=engine,
                        time_range=time_range,
                        pageno=pageno,
                        language=language,
                    )
                    return engine, list(result.get("results") or []), None
                except Exception as exc:
                    return engine, [], str(exc) or type(exc).__name__

        outcomes = await asyncio.gather(*(run_one(name) for name in engines))
        per_engine: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for engine, results, error in outcomes:
            per_engine[engine] = results
            if error:
                errors[engine] = error

        return core.ok({"query": query, "engines": per_engine, "errors": errors})
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def register(mcp: Any) -> None:
    mcp.tool()(search_compare)
