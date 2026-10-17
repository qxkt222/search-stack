"""``web_fetch`` tool: download a page and extract readable text."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .. import client, core
from ..extract import extract_content

_EXCERPT_CHARS = 300
_MAX_LINKS = 50


def validate_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("url must be a non-empty string")
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"invalid URL: {value}") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"invalid URL (http/https required): {value}")
    return value


def _excerpt(text: str) -> str:
    return " ".join(text.split())[:_EXCERPT_CHARS]


async def fetch_page(
    url: str,
    max_chars: int = 20000,
    include_links: bool = False,
) -> dict[str, Any]:
    """Implementation shared with ``search_and_fetch`` (returns an envelope)."""

    try:
        url = validate_url(url)
        core.check_int(max_chars, "max_chars", 1000, 200000)
        if not isinstance(include_links, bool):
            raise ValueError("include_links must be a boolean")

        cfg = core.get_config()
        key = core.cache_key(
            "web_fetch",
            {
                "url": core.normalize_url(url),
                "max_chars": max_chars,
                "include_links": include_links,
            },
        )
        cached = core.CACHE.get(key, cfg.fetch_ttl)
        if not core.is_missing(cached):
            return core.ok(cached)

        response = await client.fetch(url)
        final_url = str(response.url)
        if response.status_code >= 400:
            return core.err(
                f"HTTP {response.status_code} for {url}",
                status=response.status_code,
                url=url,
                final_url=final_url,
            )

        extracted = extract_content(
            response.text, final_url, include_links=include_links
        )
        text = extracted["text"]
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        payload: dict[str, Any] = {
            "url": url,
            "final_url": final_url,
            "status": response.status_code,
            "title": extracted["title"],
            "text": text,
            "excerpt": _excerpt(text),
            "chars": len(text),
            "truncated": truncated,
        }
        if include_links:
            payload["links"] = extracted["links"][:_MAX_LINKS]

        core.CACHE.set(key, payload, cfg.fetch_ttl)
        return core.ok(payload)
    except Exception as exc:
        return core.err(str(exc) or type(exc).__name__)


async def web_fetch(
    url: str,
    max_chars: int = 20000,
    include_links: bool = False,
) -> dict[str, Any]:
    """Fetch a URL and extract the main article text.

    Args:
        url: Absolute http(s) URL to fetch.
        max_chars: Maximum characters of text to return (1000-200000).
        include_links: Include up to 50 absolute links found on the page.

    Returns:
        ``{"ok": true, "result": {url, final_url, status, title, text,
        excerpt, chars, truncated, links?}}`` or ``{"ok": false, "error": "..."}``.
    """

    return await fetch_page(url, max_chars=max_chars, include_links=include_links)


def register(mcp: Any) -> None:
    mcp.tool()(web_fetch)
