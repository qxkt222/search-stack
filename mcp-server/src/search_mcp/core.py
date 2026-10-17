"""Shared primitives: envelopes, configuration, URL normalisation and caching."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

APP_NAME = "search-mcp"
VERSION = "0.1.0"

# A request is attempted once, then retried up to MAX_RETRIES times.
MAX_RETRIES = 3
RETRY_DELAYS: tuple[float, ...] = (0.5, 1.0, 2.0)

DEFAULT_SEARXNG_URL = "http://localhost:8888"
DEFAULT_TIMEOUT = 20.0
DEFAULT_SEARCH_TTL = 300.0
DEFAULT_FETCH_TTL = 3600.0

TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "yclid",
        "msclkid",
        "dclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "_gl",
        "spm",
        "ref",
        "ref_src",
        "ref_url",
        "source",
    }
)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Config:
    """Runtime configuration read from the environment."""

    searxng_url: str
    proxy: str | None
    timeout: float
    search_ttl: float
    fetch_ttl: float


def _env_number(name: str, default: float, *, allow_zero: bool = False) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value < 0 or (value == 0 and not allow_zero) or not math.isfinite(value):
        return default
    return value


def get_config() -> Config:
    """Read configuration on every call so tests/launchers can change env vars."""

    url = (os.environ.get("SEARXNG_URL") or DEFAULT_SEARXNG_URL).strip()
    url = url.rstrip("/") or DEFAULT_SEARXNG_URL
    proxy = (os.environ.get("SEARCH_MCP_PROXY") or "").strip() or None
    return Config(
        searxng_url=url,
        proxy=proxy,
        timeout=_env_number("SEARCH_MCP_TIMEOUT", DEFAULT_TIMEOUT),
        search_ttl=_env_number(
            "SEARCH_MCP_CACHE_TTL", DEFAULT_SEARCH_TTL, allow_zero=True
        ),
        fetch_ttl=_env_number(
            "SEARCH_MCP_FETCH_CACHE_TTL", DEFAULT_FETCH_TTL, allow_zero=True
        ),
    )


def mask_proxy(proxy: str | None) -> str | None:
    """Return a redacted proxy string safe to expose through MCP."""

    if not proxy:
        return None
    candidate = proxy if "://" in proxy else f"http://{proxy}"
    try:
        parts = urlsplit(candidate)
        host = parts.hostname or "***"
        return f"{parts.scheme or 'http'}://{host}:****"
    except ValueError:
        return "****"


def is_local_url(url: str) -> bool:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return False
    return host in {"localhost", "127.0.0.1", "::1"}


# --------------------------------------------------------------------------- #
# Envelopes
# --------------------------------------------------------------------------- #


def _sanitize(value: Any) -> Any:
    """Make a value JSON-safe, replacing NaN/inf floats with ``None``."""

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def ok(result: Any = None) -> dict[str, Any]:
    """Success envelope used by every tool."""

    return {"ok": True, "result": _sanitize(result)}


def err(message: Any, **extra: Any) -> dict[str, Any]:
    """Failure envelope used by every tool; never raises."""

    payload: dict[str, Any] = {"ok": False, "error": str(message) or "unknown error"}
    payload.update(_sanitize(extra))
    return payload


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def check_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def check_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def check_time_range(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if value not in {"day", "week", "month", "year"}:
        raise ValueError("time_range must be one of: day, week, month, year")
    return str(value)


def check_string_list(value: Any, name: str, low: int, high: int) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    if not low <= len(value) <= high:
        raise ValueError(f"{name} must contain between {low} and {high} items")
    cleaned: list[str] = []
    for item in value:
        cleaned.append(check_text(item, name))
    return cleaned


def check_optional_text(value: Any, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value.strip() or None


# --------------------------------------------------------------------------- #
# URL normalisation
# --------------------------------------------------------------------------- #


def _single_host(parts: Any) -> str:
    host = (parts.hostname or "").lower()
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    if port is not None:
        default = 80 if parts.scheme == "http" else 443 if parts.scheme == "https" else None
        if port != default:
            host = f"{host}:{port}"
    return host


def normalize_url(url: str) -> str:
    """Normalise a URL for dedupe/cache keys.

    Removes fragments, tracking query parameters and trailing slashes, and
    lowercases the scheme and host.
    """

    if not url:
        return ""
    raw = str(url).strip()
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw
    if not parts.scheme and not parts.netloc:
        return raw.split("#", 1)[0].rstrip("/")

    scheme = (parts.scheme or "http").lower()
    netloc = _single_host(parts)
    if not netloc and parts.netloc:
        netloc = parts.netloc.lower()

    path = parts.path or ""
    if path in {"", "/"}:
        path = ""
    else:
        path = path.rstrip("/")

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


# --------------------------------------------------------------------------- #
# TTL cache
# --------------------------------------------------------------------------- #


_now = time.monotonic
_MISSING = object()


class TTLCache:
    """Tiny thread-safe in-process TTL cache with hit/miss counters."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, key: str, ttl: float) -> Any:
        now = _now()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._misses += 1
                return _MISSING
            stored_at, value = entry
            if ttl <= 0 or now - stored_at > ttl:
                self._data.pop(key, None)
                self._misses += 1
                return _MISSING
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl: float) -> None:
        if ttl <= 0:
            return
        with self._lock:
            self._data[key] = (_now(), value)

    def clear(self) -> int:
        with self._lock:
            count = len(self._data)
            self._data.clear()
            self._hits = 0
            self._misses = 0
        return count

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._data),
                "hits": self._hits,
                "misses": self._misses,
            }


CACHE = TTLCache()


def cache_key(method: str, params: dict[str, Any]) -> str:
    packed = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return f"{method}:{packed}"


def is_missing(value: Any) -> bool:
    return value is _MISSING
