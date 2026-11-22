"""Canonicalise public HTTP(S) URLs before spending extraction credits."""

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


class InvalidUrlError(ValueError):
    """A candidate URL is malformed or outside the supported public-web subset."""


_CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f\\]")
_NUMERIC_ADDRESS_LABEL = re.compile(r"(?:0[xX][0-9a-fA-F]+|0[0-7]+|[0-9]+)\Z")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def _looks_like_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        labels = host.split(".")
        return all(_NUMERIC_ADDRESS_LABEL.fullmatch(label) for label in labels)


def validate_url(value: str) -> str:
    """Return a canonical URL or raise a non-sensitive ``InvalidUrlError``."""

    if not isinstance(value, str) or not value or len(value) > 2048:
        raise InvalidUrlError("URL is empty or too long")
    if _CONTROL_OR_SPACE.search(value):
        raise InvalidUrlError("URL contains whitespace or control characters")

    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidUrlError("URL must use HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            raise InvalidUrlError("URL credentials are not allowed")
        port = parsed.port
        if port is not None and port not in {80, 443}:
            raise InvalidUrlError("URL port is not allowed")
        raw_host = parsed.hostname
    except ValueError as exc:
        if isinstance(exc, InvalidUrlError):
            raise
        raise InvalidUrlError("URL is malformed") from None

    if not raw_host:
        raise InvalidUrlError("URL has no hostname")
    host = raw_host.rstrip(".").lower()
    if not host or host == "localhost" or "." not in host:
        raise InvalidUrlError("URL hostname is not a public domain")
    if host.endswith((".local", ".internal", ".lan")) or _looks_like_ip_literal(host):
        raise InvalidUrlError("URL hostname is not a public domain")

    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise InvalidUrlError("URL hostname is malformed") from None
    labels = ascii_host.split(".")
    if len(ascii_host) > 253 or any(not _DNS_LABEL.fullmatch(label) for label in labels):
        raise InvalidUrlError("URL hostname is malformed")

    netloc = ascii_host
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{netloc}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


_PORTAL_HOSTS = frozenset({"www.gov.pl", "gov.pl"})


def site_key(url: str) -> str:
    """The "site" a URL belongs to, used to require evidence from different sites.

    Host without ``www.``; on the gov.pl portal each institution's subsite
    (``/web/<id>``) counts as its own site (``gov.pl/web/rcb``).
    """

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host in _PORTAL_HOSTS:
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) >= 2 and segments[0] == "web":
            return f"gov.pl/web/{segments[1].lower()}"
    return host.removeprefix("www.")
