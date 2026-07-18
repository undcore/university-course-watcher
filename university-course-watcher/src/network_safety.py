from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests


class UnsafeUrlError(ValueError):
    """Raised when a crawler URL can target a non-public network endpoint."""


def require_public_http_url(url: str, resolve_host: bool = False) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").rstrip(".").lower()

    if parsed.scheme not in {"http", "https"} or not hostname:
        raise UnsafeUrlError("Only absolute HTTP(S) URLs are allowed.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("Credentials in crawler URLs are not allowed.")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeUrlError("Localhost crawler targets are not allowed.")

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []

    try:
        addresses.append(ipaddress.ip_address(hostname.strip("[]")))
    except ValueError:
        if resolve_host:
            try:
                resolved = socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise UnsafeUrlError("Crawler target hostname could not be resolved.") from exc

            addresses.extend(ipaddress.ip_address(item[4][0]) for item in resolved)

    if any(not address.is_global for address in addresses):
        raise UnsafeUrlError("Non-public IP crawler targets are not allowed.")

    return url


def is_public_http_url(url: str) -> bool:
    try:
        require_public_http_url(url)
    except UnsafeUrlError:
        return False
    return True


class SafeHttpSession(requests.Session):
    """Session that validates initial and redirected destinations before I/O."""

    def send(self, request: requests.PreparedRequest, **kwargs) -> requests.Response:
        require_public_http_url(request.url or "", resolve_host=True)
        return super().send(request, **kwargs)
