"""SSRF guard tests.

All tests inject a fake resolver, so **no network access** is required. The
resolver is a plain callable ``host -> list[ip_str]``.
"""

from __future__ import annotations

import pytest

from naijafinsent.data.http import Fetcher, SSRFBlockedError, is_safe_url


def resolver_mapping(mapping: dict[str, list[str]]):
    """Build a fake resolver from a hostname -> addresses mapping."""

    def _resolve(host: str) -> list[str]:
        if host in mapping:
            return mapping[host]
        raise OSError(f"no fake mapping for {host}")

    return _resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://localhost.localdomain/",
        "http://127.0.0.1/",
        "http://127.0.0.1:8000/health",
        "http://[::1]/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
        "http://[fe80::1]/",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com/",
        "javascript:alert(1)",
    ],
)
def test_is_safe_url_rejects_dangerous(url: str):
    ok, reason = is_safe_url(url, resolver=resolver_mapping({}))
    assert ok is False
    assert reason != "ok"


def test_is_safe_url_rejects_hostname_resolving_to_private():
    resolve = resolver_mapping({"internal.example": ["10.1.2.3"]})
    ok, reason = is_safe_url("https://internal.example/news", resolver=resolve)
    assert ok is False
    assert "non-public" in reason


def test_is_safe_url_rejects_metadata_service_name():
    # A name that resolves to the cloud metadata IP must be blocked.
    resolve = resolver_mapping({"metadata.example": ["169.254.169.254"]})
    ok, _ = is_safe_url("http://metadata.example/", resolver=resolve)
    assert ok is False


def test_is_safe_url_accepts_public_https():
    resolve = resolver_mapping({"news.example": ["93.184.216.34"]})
    ok, reason = is_safe_url("https://news.example/article/1", resolver=resolve)
    assert ok is True
    assert reason == "ok"


def test_is_safe_url_accepts_public_http():
    resolve = resolver_mapping({"news.example": ["1.1.1.1"]})
    ok, reason = is_safe_url("http://news.example/", resolver=resolve)
    assert ok is True
    assert reason == "ok"


def test_is_safe_url_rejects_when_dns_fails():
    ok, reason = is_safe_url("https://does-not-resolve.example/", resolver=resolver_mapping({}))
    assert ok is False
    assert "dns" in reason


def test_is_safe_url_rejects_empty_host():
    ok, _ = is_safe_url("http:///path", resolver=resolver_mapping({}))
    assert ok is False


def test_is_safe_url_rejects_ipv4_mapped_ipv6_loopback():
    resolve = resolver_mapping({"mixed.example": ["::ffff:127.0.0.1"]})
    ok, _ = is_safe_url("http://mixed.example/", resolver=resolve)
    assert ok is False


def test_fetcher_check_url_raises_on_blocked():
    fetcher = Fetcher(resolver=resolver_mapping({}))
    with pytest.raises(SSRFBlockedError):
        fetcher.check_url("http://127.0.0.1/secret")


def test_fetcher_check_url_passes_public():
    fetcher = Fetcher(resolver=resolver_mapping({"news.example": ["93.184.216.34"]}))
    # Should not raise.
    fetcher.check_url("https://news.example/article/1")
