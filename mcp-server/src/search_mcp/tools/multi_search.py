"""``multi_search`` tool: run several queries concurrently and merge results."""

from __future__ import annotations

import asyncio
import math
from typing import Any

from .. import client, core


def _rank(item: dict[str, Any]) -> float:
    score = item.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return float("-inf")
    value = float(score)
    return value if math.isfinite(value) else float("-inf")


def _merge_item(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    engines = existing.setdefault("engines", [])
    for name in new.get("engines", []) or [new.get("engine")]:
        if name and name not in engines:
            engines.append(name)
    if _rank(new) > _rank(existing):
        replacement = dict(new)
        replacement["engines"] = engines
        return replacement
    return existing


async def multi_search(
    queries: list[str],
    max_results: int = 5,
    concurrency: int = 4,
    dedupe: bool = True,
    categories: str | None = None,
    engines: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    pageno: int = 1,
) -> dict[str, Any]:
    """Run several SearXNG queries concurrently.

    Args:
        queries: 1-10 search queries.
        max_results: Maximum results per query (1-50).
        concurrency: Number of concurrent searches (1-8).
        dedupe: Merge duplicate URLs across queries (highest score wins).
        categories: Comma-separated SearXNG categories.
        engines: Comma-separated SearXNG engine names.
        time_range: One of day, week, month or year.
        language: Language code.
        pageno: SearXNG result page (1-10).

    Returns:
        ``{"ok": true, "result": {queries, merged, errors}}``.
    """

    try:
        queries = core.check_string_list(queries, "queries", 1, 10)
        core.check_int(max_results, "max_results", 1, 50)
        core.check_int(concurrency, "concurrency", 1, 8)
        core.check_int(pageno, "pageno", 1, 10)
        if not isinstance(dedupe, bool):
            raise ValueError("dedupe must be a boolean")
        time_range = core.check_time_range(time_range)
        categories = core.check_optional_text(categories, "categories")
        engines = core.check_optional_text(engines, "engines")
        language = core.check_optional_text(language, "language")

        unique_queries = list(dict.fromkeys(queries))
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(query: str) -> tuple[str, list[dict[str, Any]], str | None]:
            async with semaphore:
                try:
                    result = await client.search(
                        query,
                        max_results=max_results,
                        categories=categories,
                        engines=engines,
                        time_range=time_range,
                        pageno=pageno,
                        language=language,
                    )
                    return query, list(result.get("results") or []), None
                except Exception as exc:
                    return query, [], str(exc) or type(exc).__name__

        outcomes = await asyncio.gather(*(run_one(q) for q in unique_queries))

        per_query: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for query, results, error in outcomes:
            per_query[query] = results
            if error:
                errors[query] = error

        merged: list[dict[str, Any]] = []
        index: dict[str, int] = {}
        for query in unique_queries:
            for hit in per_query.get(query, []):
                url_key = core.normalize_url(str(hit.get("url") or ""))
                if not url_key:
                    url_key = f"{query}:{len(merged)}"
                copy = dict(hit)
                copy["engines"] = [copy["engine"]] if copy.get("engine") else []
                if dedupe and url_key in index:
                    position = index[url_key]
                    merged[position] = _merge_item(merged[position], copy)
                    continue
                if dedupe:
                    index[url_key] = len(merged)
                merged.append(copy)

        return core.ok({"queries": per_query, "merged": merged, "errors": errors})
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def register(mcp: Any) -> None:
    mcp.tool()(multi_search)
