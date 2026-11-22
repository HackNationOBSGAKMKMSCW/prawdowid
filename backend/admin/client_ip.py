"""Adres IP klienta i jego pseudonim do blokad po próbach prompt injection.

Adres jest potrzebny wyłącznie do blokady: do bazy trafia tylko klucz HMAC-SHA256 adresu
(``ip_key``, sól ``ADMIN_IP_SALT`` albo losowa, zapisana w bazie) i maska do pokazania w
panelu (``203.0.113.x``, ``2001:db8:1:…/64``). Zwykłe zapytania nie zapisują nic o adresie.

Skąd adres (po kolei, pierwszy poprawny):

1. ``CLIENT_IP_HEADER`` (domyślnie ``cf-connecting-ip``): nagłówek, który ustawia zaufane
   proxy i którego klient nie może podrobić. Render stoi za Cloudflare, a Cloudflare zawsze
   nadpisuje ``CF-Connecting-IP`` adresem odwiedzającego. Bez Cloudflare ustaw pustą wartość
   (``CLIENT_IP_HEADER=``), bo wtedy klient mógłby wpisać tam dowolny adres.
2. ``X-Forwarded-For``: każde proxy dopisuje na koniec listy adres, z którego przyszło
   żądanie, a klient może wpisać cokolwiek na początku. ``TRUSTED_PROXY_HOPS`` (domyślnie 1)
   to liczba zaufanych proxy przed aplikacją: bierzemy adres o tyle pozycji od końca.
   ``0`` = nagłówek jest ignorowany.
3. Adres połączenia.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
from dataclasses import dataclass
from typing import Any

HOPS_ENV = "TRUSTED_PROXY_HOPS"
HEADER_ENV = "CLIENT_IP_HEADER"
DEFAULT_HEADER = "cf-connecting-ip"


def trusted_hops() -> int:
    try:
        return max(0, int(os.getenv(HOPS_ENV, "1")))
    except ValueError:
        return 1


def trusted_header() -> str:
    return os.getenv(HEADER_ENV, DEFAULT_HEADER).strip().lower()


def _parse(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    value = value.strip().strip('"')
    if value.startswith("[") and "]" in value:  # [2001:db8::1]:443
        value = value[1 : value.index("]")]
    elif value.count(":") == 1:  # 203.0.113.7:443
        value = value.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def client_address(
    headers: dict[bytes, bytes] | Any,
    peer: str | None,
    *,
    hops: int | None = None,
    header: str | None = None,
) -> str | None:
    """Adres klienta: zaufany nagłówek, potem ``X-Forwarded-For``, potem połączenie."""
    header = trusted_header() if header is None else header.strip().lower()
    if header:
        address = _parse(_header(headers, header).split(",")[0])
        if address is not None:
            return str(address)
    hops = trusted_hops() if hops is None else hops
    if hops > 0:
        raw = _header(headers, "x-forwarded-for")
        entries = [entry.strip() for entry in raw.split(",") if entry.strip()]
        if len(entries) >= hops:
            address = _parse(entries[-hops])
            if address is not None:
                return str(address)
    address = _parse(peer)
    return str(address) if address is not None else None


def request_address(request: Any) -> str | None:
    """Adres klienta dla ``starlette.requests.Request``."""
    client = getattr(request, "client", None)
    return client_address(getattr(request, "headers", None) or {}, getattr(client, "host", None))


def _header(headers: Any, name: str) -> str:
    """Nagłówek z ``dict[bytes, bytes]`` (ASGI, małe litery) albo z ``Headers`` Starlette."""
    if isinstance(headers, dict):
        value = headers.get(name.encode()) or headers.get(name)
        return value.decode("latin-1") if isinstance(value, bytes) else (value or "")
    getter = getattr(headers, "get", None)
    return (getter(name) if getter else None) or ""


@dataclass(frozen=True)
class IpIdentity:
    key: str  # HMAC adresu (IPv6: sieci /64), bez możliwości odczytu adresu w panelu
    label: str  # maska do pokazania w panelu


def identity(address: str | None, salt: str) -> IpIdentity | None:
    """Klucz i maska adresu. IPv6 jest liczony per sieć /64 (adresy w niej się zmieniają)."""
    parsed = _parse(address)
    if parsed is None:
        return None
    if isinstance(parsed, ipaddress.IPv4Address):
        material = parsed.packed
        octets = str(parsed).split(".")
        label = ".".join([*octets[:3], "x"])
    else:
        network = ipaddress.IPv6Network(f"{parsed}/64", strict=False)
        material = network.network_address.packed[:8]
        groups = network.network_address.exploded.split(":")[:3]
        label = ":".join(group.lstrip("0") or "0" for group in groups) + ":…/64"
    key = hmac.new(salt.encode(), material, hashlib.sha256).hexdigest()[:32]
    return IpIdentity(key=key, label=label)
