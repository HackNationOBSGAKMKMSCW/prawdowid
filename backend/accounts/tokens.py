"""Tokeny dostępu w stylu AdonisJS: ``oat_<id base64url>.<sekret>``.

W bazie (``auth_access_tokens.hash``) trafia wyłącznie SHA-256 sekretu — wyciek bazy nie
daje działających tokenów. Identyfikator w tokenie pozwala znaleźć wiersz bez skanowania.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

PREFIX = "oat_"
SECRET_BYTES = 32
TOKEN_TYPE = "auth_token"


@dataclass(frozen=True)
class ParsedToken:
    token_id: int
    secret: str


def _encode_id(token_id: int) -> str:
    return base64.urlsafe_b64encode(str(token_id).encode()).decode().rstrip("=")


def _decode_id(value: str) -> int:
    padded = value + "=" * (-len(value) % 4)
    return int(base64.urlsafe_b64decode(padded.encode()).decode())


def new_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def compose(token_id: int, secret: str) -> str:
    return f"{PREFIX}{_encode_id(token_id)}.{secret}"


def parse(raw: str) -> ParsedToken | None:
    """Rozbierz token; ``None`` dla czegokolwiek, co nie ma właściwego kształtu."""
    raw = (raw or "").strip()
    if not raw.startswith(PREFIX) or raw.count(".") != 1 or len(raw) > 200:
        return None
    encoded_id, secret = raw[len(PREFIX) :].split(".")
    try:
        token_id = _decode_id(encoded_id)
    except (ValueError, UnicodeDecodeError):
        return None
    if token_id <= 0 or len(secret) < 20:
        return None
    return ParsedToken(token_id, secret)


def matches(secret: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret), stored_hash)
