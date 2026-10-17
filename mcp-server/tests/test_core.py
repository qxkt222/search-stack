"""Unit tests for core helpers (envelopes, URLs, cache, config)."""

from __future__ import annotations

import json

import pytest

from search_mcp import core


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://Example.COM/Path/?utm_source=a&b=2&fbclid=z#frag",
            "https://example.com/Path?b=2",
        ),
        ("https://Example.com/", "https://example.com"),
        ("http://example.com:80/a/", "http://example.com/a"),
        ("https://example.com:8443/a//", "https://example.com:8443/a"),
        ("https://example.com/a?utm_medium=x", "https://example.com/a"),
        ("https://example.com/A?x=1&utm_campaign=y#z", "https://example.com/A?x=1"),
        ("", ""),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert core.normalize_url(raw) == expected


def test_normalize_url_dedupes_tracking_variants() -> None:
    first = "https://Example.com/page/?utm_source=newsletter&id=7#top"
    second = "https://example.com/page?id=7"
    assert core.normalize_url(first) == core.normalize_url(second)


def test_cache_hit_miss_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [100.0]
    monkeypatch.setattr(core, "_now", lambda: now[0])
    cache = core.TTLCache()

    assert core.is_missing(cache.get("key", 10))
    cache.set("key", {"value": 1}, 10)
    assert cache.get("key", 10) == {"value": 1}
    assert cache.stats() == {"entries": 1, "hits": 1, "misses": 1}

    now[0] = 111.0
    assert core.is_missing(cache.get("key", 10))
    assert cache.stats() == {"entries": 0, "hits": 1, "misses": 2}

    cache.set("other", 2, 10)
    assert cache.clear() == 1
    assert cache.stats() == {"entries": 0, "hits": 0, "misses": 0}


def test_cache_ttl_zero_disables_storage() -> None:
    cache = core.TTLCache()
    cache.set("key", "value", 0)
    assert core.is_missing(cache.get("key", 0))
    assert cache.stats()["entries"] == 0


def test_ok_envelope_is_json_safe() -> None:
    envelope = core.ok(
        {"nan": float("nan"), "inf": float("inf"), "nested": [float("-inf"), 1.5]}
    )
    encoded = json.dumps(envelope, allow_nan=False)
    assert '"nan": null' in encoded
    assert envelope["result"]["nan"] is None
    assert envelope["result"]["nested"] == [None, 1.5]


def test_err_envelope() -> None:
    envelope = core.err("boom", status=500)
    assert envelope == {"ok": False, "error": "boom", "status": 500}
    assert core.err("") ["error"] == "unknown error"


def test_config_defaults() -> None:
    cfg = core.get_config()
    assert cfg.searxng_url == "http://localhost:8888"
    assert cfg.proxy is None
    assert cfg.timeout == 20.0
    assert cfg.search_ttl == 300.0
    assert cfg.fetch_ttl == 3600.0


def test_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.test:9999///")
    monkeypatch.setenv("SEARCH_MCP_PROXY", "http://proxy.example:3128")
    monkeypatch.setenv("SEARCH_MCP_TIMEOUT", "3.5")
    monkeypatch.setenv("SEARCH_MCP_CACHE_TTL", "60")
    monkeypatch.setenv("SEARCH_MCP_FETCH_CACHE_TTL", "120")

    cfg = core.get_config()
    assert cfg.searxng_url == "http://searxng.test:9999"
    assert cfg.proxy == "http://proxy.example:3128"
    assert cfg.timeout == 3.5
    assert cfg.search_ttl == 60.0
    assert cfg.fetch_ttl == 120.0


def test_config_ignores_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_MCP_TIMEOUT", "not-a-number")
    monkeypatch.setenv("SEARCH_MCP_CACHE_TTL", "-5")

    cfg = core.get_config()
    assert cfg.timeout == 20.0
    assert cfg.search_ttl == 300.0


def test_mask_proxy_redacts_port_and_credentials() -> None:
    masked = core.mask_proxy("http://user:secret@proxy.example:3128")
    assert masked == "http://proxy.example:****"
    assert "3128" not in masked
    assert "secret" not in masked
    assert core.mask_proxy(None) is None


def test_check_int_rejects_bool_and_out_of_range() -> None:
    with pytest.raises(ValueError):
        core.check_int(True, "n", 1, 5)
    with pytest.raises(ValueError):
        core.check_int(0, "n", 1, 5)
    assert core.check_int(3, "n", 1, 5) == 3
