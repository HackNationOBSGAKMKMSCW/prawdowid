"""Hashowanie haseł: scrypt z biblioteki standardowej (bez dodatkowych zależności).

Format: ``scrypt$<n>$<r>$<p>$<sól base64>$<hash base64>`` — parametry zapisane przy
haśle pozwalają je kiedyś podnieść bez unieważniania starych kont (``needs_rehash``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**15, 8, 1
KEY_LENGTH = 32
SALT_BYTES = 16
MIN_LENGTH = 10
MAX_LENGTH = 256
_MAXMEM = 64 * 1024 * 1024


class WeakPasswordError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=KEY_LENGTH
    )


def validate(password: str, *, email: str | None = None) -> None:
    if len(password) < MIN_LENGTH:
        raise WeakPasswordError(f"Hasło musi mieć co najmniej {MIN_LENGTH} znaków.")
    if len(password) > MAX_LENGTH:
        raise WeakPasswordError(f"Hasło może mieć najwyżej {MAX_LENGTH} znaków.")
    if len(set(password)) < 4:
        raise WeakPasswordError("Hasło jest zbyt przewidywalne.")
    if email and password.strip().lower() in {email.lower(), email.split("@")[0].lower()}:
        raise WeakPasswordError("Hasło nie może być takie jak adres email.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str) -> bool:
    parts = encoded.split("$")
    return len(parts) != 6 or parts[0] != "scrypt" or parts[1:4] != [str(N), str(R), str(P)]


# Hash do porównania, gdy konto nie istnieje: wyrównuje czas odpowiedzi
# (nie da się sprawdzić, czy email jest zarejestrowany, mierząc czas logowania).
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
