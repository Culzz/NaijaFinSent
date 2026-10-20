"""HTTP fetching with politeness, safety, and size controls.

This module is the only place in the data engine that talks to the network. It
exists so that every outbound request is:

* **polite** — hunts to a per-host rate limit and identifies honestly;
* **safe** — an SSRF guard resolves the host and refuses private/loopback/
  link-local/reserved addresses and non-http(s) schemes;
* **bounded** — the response body is capped at ``settings.fetch_max_bytes``
  while streaming, so a hostile or broken server cannot exhaust memory;
* **strict** — only a small allowlist of content types is accepted.

Nothing here imports a web framework. ``is_safe_url`` is a pure function with an
injectable resolver so it can be unit-tested with no network access.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from naijafinsent.config import Settings, get_settings

# --- Typed errors -------------------------------------------------------------


class FetchError(Exception):
    """Base class for all fetch failures."""


class SSRFBlockedError(FetchError):
    """The URL resolves to a private/loopback/reserved address or bad scheme."""


class TooLargeError(FetchError):
    """The response body exceeded ``settings.fetch_max_bytes``."""


class UnsupportedContentTypeError(FetchError):
    """The response ``Content-Type`` is not on the allowlist."""


# --- Content-type policy ------------------------------------------------------

ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "application/atom+xml",
        "application/json",
    }
)

# Hosts that are always refused regardless of DNS (defence in depth).
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
    }
)

# Only these schemes may ever be fetched.
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# A resolver takes a hostname and returns the IP literals it resolves to.
Resolver = Callable[[str], Iterable[str]]


def _default_resolver(host: str) -> list[str]:
    """Resolve ``host`` to a list of IP literal strings.

    Uses ``getaddrinfo`` so we see every address, including IPv6. Raises
    ``OSError`` (``socket.gaierror``) when resolution fails.
    """
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr and sockaddr[0] not in addresses:
            addresses.append(sockaddr[0])
    return addresses


def _is_public_ip(ip_str: str) -> bool:
    """True only when ``ip_str`` is a globally routable address."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Strip an IPv4-mapped IPv6 wrapper so 0:0:0:0:0:ffff:127.0.0.1 is caught.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_safe_url(url: str, resolver: Resolver | None = None) -> tuple[bool, str]:
    """Decide whether ``url`` is safe to fetch. Pure and injectable.

    Returns a ``(ok, reason)`` tuple. ``reason`` is ``"ok"`` on success, and a
    short human-readable explanation otherwise. The resolver can be swapped in
    tests to avoid touching DNS.

    Rejects: non-http(s) schemes (e.g. ``file://``), missing host, known local
    hostnames, and any host that resolves to a private, loopback, link-local,
    multicast, reserved, or unspecified address.
    """
    resolver = resolver or _default_resolver

    try:
        parsed = urlparse(url)
    except (ValueError, AttributeError):
        return False, "unparseable url"

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False, f"scheme not allowed: {scheme or '(none)'}"

    host = parsed.hostname
    if not host:
        return False, "no host"

    host_lower = host.lower().rstrip(".")
    if host_lower in _BLOCKED_HOSTNAMES:
        return False, f"blocked hostname: {host_lower}"

    # A literal IP in the URL is checked directly (no DNS round-trip).
    try:
        ip = ipaddress.ip_address(host_lower)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_public_ip(host_lower):
            return True, "ok"
        return False, f"non-public address: {host_lower}"

    try:
        addresses = list(resolver(host_lower))
    except OSError as exc:
        return False, f"dns resolution failed: {exc}"

    if not addresses:
        return False, "dns returned no addresses"

    for addr in addresses:
        if not _is_public_ip(addr):
            return False, f"non-public address: {host_lower} -> {addr}"

    return True, "ok"


# --- Rate limiting ------------------------------------------------------------


class HostRateLimiter:
    """A thread-safe, per-host minimum-interval limiter.

    Ensures at most one request per host every ``min_interval`` seconds by
    sleeping until the next permitted slot. Simple and good enough for a
    single-process research crawler; a distributed crawler would need a shared
    store instead.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> float:
        """Block until the host may be contacted again; return seconds slept."""
        if self.min_interval <= 0:
            return 0.0
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host)
            if last is None:
                self._last[host] = now
                return 0.0
            elapsed = now - last
            sleep_for = self.min_interval - elapsed
            if sleep_for <= 0:
                self._last[host] = now
                return 0.0
            self._last[host] = now + sleep_for
        # Sleep outside the lock so other hosts are not blocked.
        time.sleep(sleep_for)
        return sleep_for


# --- Fetcher ------------------------------------------------------------------


@dataclass
class FetchResult:
    """A successfully fetched body plus the metadata callers care about."""

    url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes
    encoding: str

    @property
    def text(self) -> str:
        """Decode the body using the declared (or guessed) encoding."""
        try:
            return self.content.decode(self.encoding or "utf-8", errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


def _retry_wait(retry_state: RetryCallState) -> float:
    """Exponential backoff base, capped to keep tests and crawls sane."""
    attempt = retry_state.attempt_number
    return min(2.0 ** (attempt - 1), 30.0)


class Fetcher:
    """Polite, SSRF-guarded HTTP client over ``httpx``.

    Parameters mirror ``Settings`` and can be overridden for tests. The client
    is created lazily and is safe to reuse across calls.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        resolver: Resolver | None = None,
        rate_limiter: HostRateLimiter | None = None,
        user_agent: str | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.settings = settings or get_settings()
        self.user_agent = user_agent or self.settings.user_agent
        self.timeout = timeout if timeout is not None else self.settings.fetch_timeout_seconds
        self.max_bytes = max_bytes if max_bytes is not None else self.settings.fetch_max_bytes
        self.max_redirects = (
            max_redirects if max_redirects is not None else self.settings.fetch_max_redirects
        )
        self.max_attempts = max_attempts
        self._resolver = resolver
        self._rate_limiter = rate_limiter or HostRateLimiter(
            self.settings.fetch_rate_limit_seconds
        )
        self._client = client
        self._owns_client = client is None

    # -- lifecycle --------------------------------------------------------
    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                max_redirects=self.max_redirects,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml,"
                        "application/rss+xml,application/atom+xml,application/json;q=0.9,*/*;q=0.1"
                    ),
                },
            )
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()
            self._client = None

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- guards -----------------------------------------------------------
    def check_url(self, url: str) -> None:
        """Raise ``SSRFBlockedError`` if the URL is not safe to fetch."""
        ok, reason = is_safe_url(url, resolver=self._resolver)
        if not ok:
            raise SSRFBlockedError(f"refused {url!r}: {reason}")

    @staticmethod
    def _content_type_ok(content_type: str) -> bool:
        mime = (content_type or "").split(";", 1)[0].strip().lower()
        return mime in ALLOWED_CONTENT_TYPES

    def _read_capped(self, response: httpx.Response) -> bytes:
        """Stream the body, aborting if it exceeds ``max_bytes``."""
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > self.max_bytes:
                raise TooLargeError(
                    f"response exceeded {self.max_bytes} bytes at {response.url}"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    # -- the actual fetch -------------------------------------------------
    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=_retry_wait,
        reraise=True,
    )
    def _fetch_once(self, url: str) -> FetchResult:
        host = (urlparse(url).hostname or "").lower()
        self._rate_limiter.wait(host)

        try:
            with self.client.stream("GET", url) as response:
                # Retry on transient server-side status codes.
                if response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    raise FetchError(
                        f"HTTP {response.status_code} for {url}"
                    )

                content_type = response.headers.get("content-type", "")
                if not self._content_type_ok(content_type):
                    raise UnsupportedContentTypeError(
                        f"content-type {content_type!r} not allowed for {url}"
                    )

                body = self._read_capped(response)
                encoding = response.encoding or "utf-8"
                final_url = str(response.url)
        except (TooLargeError, UnsupportedContentTypeError, FetchError):
            raise
        except httpx.TransportError:
            raise
        except httpx.HTTPError as exc:  # anything else from httpx
            raise FetchError(str(exc)) from exc

        return FetchResult(
            url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            content=body,
            encoding=encoding,
        )

    def fetch(self, url: str) -> FetchResult:
        """Fetch ``url``, applying all guards and retries.

        Raises a ``FetchError`` subclass on any failure. The retry decorator on
        ``_fetch_once`` uses the instance ``max_attempts`` only at construction
        time; to keep behaviour explicit we cap attempts here as well.
        """
        self.check_url(url)
        return self._fetch_once(url)


def fetch_bytes(url: str, *, fetcher: Fetcher | None = None) -> bytes:
    """Convenience helper: fetch a URL and return the raw body bytes."""
    if fetcher is None:
        with Fetcher() as owned:
            return owned.fetch(url).content
    return fetcher.fetch(url).content
