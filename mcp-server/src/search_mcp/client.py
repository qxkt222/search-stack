"""Async HTTP client shared by all tools."""

from __future__ import annotations

import asyncio
import math
from typing import Any

import httpx

from . import core

USER_AGENT = (
    f"{core.APP_NAME}/{core.VERSION} "
    "(+https://github.com/qxkt222/search-stack)"
)

_transport: httpx.AsyncBaseTransport | None = None
_clients: dict[tuple[bool, int], httpx.AsyncClient] = {}


class UpstreamError(Exception):
    """A network/upstream failure with an optional HTTP status."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Install an ``httpx.MockTransport`` (tests) or ``None`` for real network."""

    global _transport
    _transport = transport
    reset_clients()


def reset_clients() -> None:
    """Forget cached clients. Used when the transport or event loop changes."""

    _clients.clear()


async def aclose() -> None:
    clients = list(_clients.values())
    _clients.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - best effort cleanup
            pass


async def get_client(use_proxy: bool | None = None) -> httpx.AsyncClient:
    """Return a reusable ``AsyncClient`` for the current event loop."""

    cfg = core.get_config()
    if use_proxy is None:
        use_proxy = bool(cfg.proxy)
    if use_proxy and not cfg.proxy:
        use_proxy = False

    loop_id = id(asyncio.get_running_loop())
    key = (bool(use_proxy), loop_id)
    existing = _clients.get(key)
    if existing is not None and not existing.is_closed:
        return existing

    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(cfg.timeout),
        "follow_redirects": True,
        "headers": {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
        "limits": httpx.Limits(max_connections=20, max_keepalive_connections=10),
        "trust_env": False,
    }
    if _transport is not None:
        kwargs["transport"] = _transport
    if use_proxy and cfg.proxy:
        kwargs["proxy"] = cfg.proxy

    client = httpx.AsyncClient(**kwargs)
    _clients[key] = client
    return client


def retry_delay(attempt: int) -> float:
    if not core.RETRY_DELAYS:
        return 0.0
    if attempt >= len(core.RETRY_DELAYS):
        return core.RETRY_DELAYS[-1]
    return core.RETRY_DELAYS[attempt]


async def request_with_retry(
    method: str,
    url: str,
    *,
    use_proxy: bool | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Perform a request, retrying network errors and 5xx responses.

    4xx responses are returned immediately (never retried).
    """

    attempts = core.MAX_RETRIES + 1
    last_error = "unknown error"
    client = await get_client(use_proxy)
    for attempt in range(attempts):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < core.MAX_RETRIES:
                await asyncio.sleep(retry_delay(attempt))
                continue
            raise UpstreamError(
                f"request failed after {attempts} attempts: {last_error}"
            ) from exc
        if response.status_code >= 500 and attempt < core.MAX_RETRIES:
            last_error = f"HTTP {response.status_code}"
            await asyncio.sleep(retry_delay(attempt))
            continue
        return response
    raise UpstreamError(f"request failed after {attempts} attempts: {last_error}")


# --------------------------------------------------------------------------- #
# SearXNG
# --------------------------------------------------------------------------- #


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _map_search(data: dict[str, Any], query: str, max_results: int) -> dict[str, Any]:
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        raw_results = []

    items: list[dict[str, Any]] = []
    for raw in raw_results:
        if not isinstance(raw, dict):
            continue
        engine = raw.get("engine")
        if not engine and isinstance(raw.get("engines"), list) and raw["engines"]:
            engine = raw["engines"][0]
        items.append(
            {
                "title": str(raw.get("title") or ""),
                "url": str(raw.get("url") or ""),
                "content": str(raw.get("content") or ""),
                "engine": str(engine or ""),
                "score": _score(raw.get("score")),
                "category": str(raw.get("category") or ""),
            }
        )

    if any(item["score"] is not None for item in items):
        items.sort(
            key=lambda item: (
                item["score"] if item["score"] is not None else float("-inf")
            ),
            reverse=True,
        )
    items = items[:max_results]

    engines_used: list[str] = []
    for item in items:
        engine_name = item["engine"]
        if engine_name and engine_name not in engines_used:
            engines_used.append(engine_name)

    number = data.get("number_of_results")
    if isinstance(number, bool) or not isinstance(number, int):
        number = len(items)

    return {
        "query": query,
        "number_of_results": number,
        "results": items,
        "engines_used": engines_used,
    }


async def search_raw(params: dict[str, Any]) -> dict[str, Any]:
    """Call ``/search?format=json`` and return the decoded JSON body."""

    cfg = core.get_config()
    query_params: dict[str, Any] = {
        "q": params["q"],
        "format": "json",
        "pageno": params.get("pageno", 1),
    }
    for name in ("language", "categories", "engines", "time_range"):
        value = params.get(name)
        if value:
            query_params[name] = value

    response = await request_with_retry(
        "GET",
        f"{cfg.searxng_url}/search",
        use_proxy=not core.is_local_url(cfg.searxng_url),
        params=query_params,
    )
    if response.status_code >= 400:
        raise UpstreamError(
            f"SearXNG returned HTTP {response.status_code}",
            status=response.status_code,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise UpstreamError("SearXNG returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise UpstreamError("SearXNG returned an unexpected JSON payload")
    return data


async def search(
    query: str,
    *,
    max_results: int = 10,
    categories: str | None = None,
    engines: str | None = None,
    time_range: str | None = None,
    pageno: int = 1,
    language: str | None = None,
) -> dict[str, Any]:
    """Run a cached SearXNG search and return the mapped result object."""

    cfg = core.get_config()
    params = {
        "q": query,
        "max_results": max_results,
        "categories": categories,
        "engines": engines,
        "time_range": time_range,
        "pageno": pageno,
        "language": language,
    }
    key = core.cache_key("web_search", params)
    cached = core.CACHE.get(key, cfg.search_ttl)
    if not core.is_missing(cached):
        return cached

    data = await search_raw(params)
    mapped = _map_search(data, query, max_results)
    core.CACHE.set(key, mapped, cfg.search_ttl)
    return mapped


async def fetch(url: str, use_proxy: bool | None = None) -> httpx.Response:
    """Fetch an arbitrary URL, honouring ``SEARCH_MCP_PROXY``."""

    cfg = core.get_config()
    if use_proxy is None:
        use_proxy = bool(cfg.proxy)
    return await request_with_retry("GET", url, use_proxy=use_proxy)
