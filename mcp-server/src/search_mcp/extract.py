"""HTML to readable text extraction for ``web_fetch``."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import trafilatura
from bs4 import BeautifulSoup

from .core import normalize_url

_BLOCK_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "canvas")
_MAX_LINKS = 50


def _parse(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _clean_text(value: str) -> str:
    lines = []
    for line in value.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _fallback_text(soup: BeautifulSoup) -> str:
    for tag in soup(_BLOCK_TAGS):
        tag.decompose()
    return _clean_text(soup.get_text("\n"))


def _title(soup: BeautifulSoup) -> str:
    if soup.title is not None:
        value = soup.title.get_text(" ", strip=True)
        if value:
            return value
    heading = soup.find("h1")
    if heading is not None:
        return heading.get_text(" ", strip=True)
    return ""


def _links(soup: BeautifulSoup, base_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        absolute = urljoin(base_url, href)
        try:
            parts = urlsplit(absolute)
        except ValueError:
            continue
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            continue
        absolute = absolute.split("#", 1)[0]
        key = normalize_url(absolute)
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(absolute)
        if len(found) >= _MAX_LINKS:
            break
    return found


def extract_content(
    html: str,
    base_url: str,
    *,
    include_links: bool = False,
) -> dict[str, Any]:
    """Extract title, main text and (optionally) absolute links from HTML."""

    soup = _parse(html)
    title = _title(soup)

    text: str | None = None
    try:
        text = trafilatura.extract(
            html,
            url=base_url,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
    except Exception:
        text = None

    if not text or not text.strip():
        text = _fallback_text(soup)
    else:
        text = _clean_text(text)

    return {
        "title": title,
        "text": text,
        "links": _links(soup, base_url) if include_links else [],
    }
