"""Health, cache and configuration tools."""

from __future__ import annotations

from typing import Any

from .. import client, core


async def health_check() -> dict[str, Any]:
    """Check SearXNG reachability, the search endpoint, proxy and cache.

    Returns:
        ``{"ok": true, "result": {ok, searxng, search, proxy, cache}}``.
        ``result.ok`` is false when either the health endpoint or a probe
        search fails (the envelope itself still reports that the check ran).
    """

    try:
        cfg = core.get_config()
        use_proxy = not core.is_local_url(cfg.searxng_url)

        searxng: dict[str, Any] = {"url": cfg.searxng_url, "ok": False}
        try:
            response = await client.request_with_retry(
                "GET", f"{cfg.searxng_url}/healthz", use_proxy=use_proxy
            )
            healthy = 200 <= response.status_code < 300
            searxng["status"] = response.status_code
            searxng["ok"] = healthy
            if not healthy:
                searxng["error"] = f"HTTP {response.status_code}"
        except Exception as exc:
            searxng["error"] = str(exc) or type(exc).__name__

        search: dict[str, Any] = {"ok": False, "query": "test"}
        try:
            probe = await client.search("test", max_results=1)
            search["ok"] = True
            search["number_of_results"] = probe.get("number_of_results", 0)
            search["results_count"] = len(probe.get("results") or [])
        except Exception as exc:
            search["error"] = str(exc) or type(exc).__name__

        payload = {
            "ok": bool(searxng.get("ok") and search.get("ok")),
            "searxng": searxng,
            "search": search,
            "proxy": {
                "configured": bool(cfg.proxy),
                "masked": core.mask_proxy(cfg.proxy),
            },
            "cache": core.CACHE.stats(),
        }
        return core.ok(payload)
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def cache_stats() -> dict[str, Any]:
    """Return in-process cache entry, hit and miss counters."""

    try:
        return core.ok(core.CACHE.stats())
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def cache_clear() -> dict[str, Any]:
    """Clear all cached searches and fetched pages."""

    try:
        cleared = core.CACHE.clear()
        return core.ok({"cleared": cleared, "entries": 0})
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def config_info() -> dict[str, Any]:
    """Return the effective SearXNG URL, timeout, cache TTLs and proxy status."""

    try:
        cfg = core.get_config()
        return core.ok(
            {
                "searxng_url": cfg.searxng_url,
                "timeout": cfg.timeout,
                "cache_ttl": {
                    "search": cfg.search_ttl,
                    "fetch": cfg.fetch_ttl,
                },
                "proxy": {
                    "configured": bool(cfg.proxy),
                    "masked": core.mask_proxy(cfg.proxy),
                },
            }
        )
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


def register(mcp: Any) -> None:
    mcp.tool()(health_check)
    mcp.tool()(cache_stats)
    mcp.tool()(cache_clear)
    mcp.tool()(config_info)
