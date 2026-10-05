"""Shared outbound HTTP client and URL guardrails.

awtrixng-mgr calls URLs typed by the user. Blocking RFC1918 would be absurd:
reaching the LAN is the whole point of the product. We therefore keep only the
protections that do not get in the way of legitimate use.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.errors import UnsafeUrlError

#: Networks refused whatever the configuration says.
_DENIED = (
    ipaddress.ip_network("169.254.0.0/16"),  # cloud metadata / link-local
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/32"),
    ipaddress.ip_network("::/128"),
)


def validate_url(raw: str) -> str:
    """Validate an outbound URL, or raise UnsafeUrlError."""
    try:
        parsed = urlparse(raw)
    except ValueError as exc:
        raise UnsafeUrlError(
            f"Invalid URL: {exc}", code="url.invalid", params={"reason": str(exc)}
        ) from exc

    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(
            "Only http and https are accepted.", code="url.bad_scheme"
        )
    if not parsed.hostname:
        raise UnsafeUrlError("The URL has no host.", code="url.no_host")

    _assert_host_allowed(parsed.hostname)
    return raw


def _assert_host_allowed(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(
            f"Host not found: {host}", code="url.host_not_found", params={"host": host}
        ) from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        for network in _DENIED:
            if address in network:
                raise UnsafeUrlError(
                    f"Address refused: {address}",
                    code="url.address_refused",
                    params={"address": str(address)},
                )


def build_client(
    *,
    auth: tuple[str, str] | None = None,
    verify: bool = True,
    base_url: str = "",
) -> httpx.AsyncClient:
    """httpx client with hard timeouts and redirects disabled."""
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=base_url,
        auth=auth,
        verify=verify,
        follow_redirects=False,
        timeout=httpx.Timeout(
            connect=settings.http_connect_timeout,
            read=settings.http_read_timeout,
            write=settings.http_read_timeout,
            pool=settings.http_connect_timeout,
        ),
    )
