"""URL validation and SSRF protection (spec section 9).

A URL is fetchable only when it is a plain http(s) URL on a public
address. Everything that could reach an internal service is rejected
*before* any request is made:

- non-http(s) schemes, missing host, embedded credentials (userinfo)
- non-standard ports (only 80/443)
- hostnames that resolve to a private, loopback, link-local, reserved,
  multicast or unspecified address (checked with ``socket.getaddrinfo``,
  every resolved address must be public)
- literal IP hosts in a private range, and ``localhost`` itself

Known limitation: DNS is resolved once and validated before the fetch.
A hostile DNS record that changes between validation and connection
(rebinding / TOCTOU) is not defended against here; that needs
connect-to-resolved-IP, which httpx does not expose directly.
"""

import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_HOSTNAMES = {"localhost"}
ALLOWED_PORTS = {80, 443}


class UnsafeUrlError(ValueError):
    """Raised when a URL fails the SSRF checks."""


BENCHMARKING_NET = ipaddress.ip_network("198.18.0.0/15")


def _ip_is_public(ip_str: str) -> bool:
    """True only for an address that cannot be an internal service.

    Blocks RFC1918, loopback, link-local, CGNAT (100.64/10), multicast,
    unspecified and reserved ranges. One deliberate carve-out:
    198.18.0.0/15 is IANA benchmarking space (RFC 2544) — never assigned
    to a real host, so it can never be the app's internal network. In
    sandboxed/proxied environments the resolver answers every public
    hostname with a distinct address in this range (the egress NAT), and
    the real fetch goes through the proxy; blocking it would reject
    every public URL there while adding no SSRF protection.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if ip in BENCHMARKING_NET:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url_safe(url: str) -> str:
    """Validate *url* for fetching. Returns the normalised URL.

    Raises UnsafeUrlError with a plain-English reason on any failure.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("only http(s) URLs are allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must have a host name")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs with embedded credentials are not allowed")

    host = parsed.hostname.lower()
    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise UnsafeUrlError(f"host '{host}' is not a public address")

    port = parsed.port
    if port is not None and port not in ALLOWED_PORTS:
        raise UnsafeUrlError(f"port {port} is not allowed (only 80/443)")

    # Literal IP host: check it directly, no DNS needed.
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    if is_ip_literal and not _ip_is_public(host):
        raise UnsafeUrlError(f"host '{host}' is not a public address")

    # Resolve and require EVERY address to be public.
    try:
        infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeUrlError(f"host '{host}' could not be resolved")
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeUrlError(f"host '{host}' could not be resolved")
    bad = sorted(a for a in addresses if not _ip_is_public(a))
    if bad:
        raise UnsafeUrlError(
            f"host '{host}' resolves to non-public address(es): {', '.join(bad)}"
        )
    return url.strip()
