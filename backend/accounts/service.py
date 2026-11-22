"""Konta, logowanie i tokeny dostępu (tabele ``users`` i ``auth_access_tokens``)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from database import Database
from psycopg import errors

from . import passwords, permissions, tokens
from .activity import ActivityLog, Actor

TOKEN_TTL = timedelta(hours=8)
MAX_TOKEN_TTL = timedelta(days=90)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_MAX_FAILURES = 5
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")

USER_COLUMNS = (
    "id, name, email, role::text AS role, is_active, last_login_at, created_at, updated_at"
)


class AccountError(ValueError):
    """Błąd po stronie danych wejściowych (komunikat po polsku, można pokazać)."""


class AuthenticationError(Exception):
    """Zły email/hasło albo konto nieaktywne — zawsze ten sam komunikat."""


class TooManyAttempts(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Za dużo nieudanych prób logowania.")
        self.retry_after = retry_after


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str
    last_login_at: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> User:
        return cls(
            id=row["id"],
            name=row["name"],
            email=row["email"],
            role=row["role"],
            is_active=row["is_active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login_at=row.get("last_login_at"),
        )

    def public(self) -> dict[str, Any]:
        """Kształt ``User`` z kontraktu panelu (bez hasła)."""
        return {
            "id": str(self.id),
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "active": self.is_active,
            "createdAt": self.created_at,
            "lastLoginAt": self.last_login_at,
        }

    def actor(self, ip: str | None = None, user_agent: str | None = None) -> Actor:
        return Actor(self.email, self.id, ip, user_agent)


@dataclass(frozen=True)
class AccessToken:
    id: int
    user_id: int
    name: str | None
    abilities: list[str]
    created_at: str
    last_used_at: str | None
    expires_at: str | None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "abilities": self.abilities,
            "createdAt": self.created_at,
            "lastUsedAt": self.last_used_at,
            "expiresAt": self.expires_at,
        }


@dataclass(frozen=True)
class IssuedToken:
    token: str  # pokazywany tylko raz
    access: AccessToken


@dataclass(frozen=True)
class Authenticated:
    user: User
    token: AccessToken

    def can(self, permission: str) -> bool:
        return permissions.allowed(self.user.role, self.token.abilities, permission)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def normalize_email(email: str) -> str:
    value = (email or "").strip()
    if not _EMAIL.match(value) or len(value) > 255:
        raise AccountError("Podaj poprawny adres email.")
    return value.lower()


def _token_from_row(row: dict[str, Any]) -> AccessToken:
    return AccessToken(
        id=row["id"],
        user_id=row["tokenable_id"],
        name=row["name"],
        abilities=json.loads(row["abilities"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        expires_at=row["expires_at"],
    )


class AccountService:
    def __init__(
        self,
        db: Database,
        *,
        activity: ActivityLog | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.activity = activity or ActivityLog(db)
        self._clock = clock or (lambda: datetime.now(UTC))

    def now(self) -> datetime:
        return self._clock()

    # --- konta -------------------------------------------------------------------------

    def create_user(
        self,
        *,
        name: str,
        email: str,
        password: str,
        role: str = "user",
        actor: Actor | None = None,
    ) -> User:
        name = " ".join((name or "").split())
        if not 1 <= len(name) <= 100:
            raise AccountError("Imię i nazwisko: od 1 do 100 znaków.")
        if role not in permissions.ROLES:
            raise AccountError(f"Nieznana rola: {role}.")
        email = normalize_email(email)
        try:
            passwords.validate(password, email=email)
        except passwords.WeakPasswordError as exc:
            raise AccountError(str(exc)) from None
        now = _iso(self.now())
        try:
            row = self.db.fetch_one(
                "INSERT INTO users (name, email, password_hash, role, created_at, updated_at) "
                f"VALUES (%s, %s, %s, %s::user_role, %s, %s) RETURNING {USER_COLUMNS}",
                [name, email, passwords.hash_password(password), role, now, now],
            )
        except errors.UniqueViolation:
            raise AccountError("Konto z tym adresem email już istnieje.") from None
        user = User.from_row(row)
        self.activity.record(
            "user.created",
            actor or user.actor(),
            subject_type="user",
            subject_id=user.id,
            details={"email": user.email, "role": user.role},
        )
        return user

    def get_user(self, user_id: int) -> User | None:
        row = self.db.fetch_one(f"SELECT {USER_COLUMNS} FROM users WHERE id = %s", [user_id])
        return User.from_row(row) if row else None

    def find_by_email(self, email: str) -> User | None:
        row = self.db.fetch_one(
            f"SELECT {USER_COLUMNS} FROM users WHERE lower(email) = lower(%s)", [email.strip()]
        )
        return User.from_row(row) if row else None

    def list_users(
        self, *, role: str | None = None, active: bool | None = None, search: str | None = None
    ) -> list[User]:
        where, params = [], []
        if role:
            where.append("role = %s::user_role")
            params.append(role)
        if active is not None:
            where.append("is_active = %s")
            params.append(active)
        if search:
            where.append("(name ILIKE %s OR email ILIKE %s)")
            pattern = "%" + search.replace("%", "").replace("_", "") + "%"
            params += [pattern, pattern]
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.db.fetch_all(
            f"SELECT {USER_COLUMNS} FROM users {clause} ORDER BY created_at, id", params
        )
        return [User.from_row(row) for row in rows]

    def update_user(
        self,
        user_id: int,
        *,
        actor: Actor,
        name: str | None = None,
        role: str | None = None,
        active: bool | None = None,
    ) -> User:
        user = self.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        changes: dict[str, Any] = {}
        if name is not None:
            name = " ".join(name.split())
            if not 1 <= len(name) <= 100:
                raise AccountError("Imię i nazwisko: od 1 do 100 znaków.")
            changes["name"] = name
        if role is not None and role != user.role:
            if role not in permissions.ROLES:
                raise AccountError(f"Nieznana rola: {role}.")
            changes["role"] = role
        if active is not None and active != user.is_active:
            changes["is_active"] = active
        if not changes:
            return user
        self._guard_last_admin(user, changes)
        assignments = ", ".join(
            f"{column} = %s::user_role" if column == "role" else f"{column} = %s"
            for column in changes
        )
        row = self.db.fetch_one(
            f"UPDATE users SET {assignments}, updated_at = %s WHERE id = %s RETURNING {USER_COLUMNS}",
            [*changes.values(), _iso(self.now()), user_id],
        )
        updated = User.from_row(row)
        if "role" in changes or changes.get("is_active") is False:
            # nowa rola albo dezaktywacja: stare tokeny nie mogą zachować dawnych uprawnień
            self.revoke_all_tokens(user_id)
        self.activity.record(
            "user.updated",
            actor,
            subject_type="user",
            subject_id=user_id,
            details={
                key: {"old": getattr(user, "is_active" if key == "is_active" else key), "new": v}
                for key, v in changes.items()
            },
        )
        return updated

    def _guard_last_admin(self, user: User, changes: dict[str, Any]) -> None:
        losing_admin = user.role == "admin" and (
            changes.get("role", "admin") != "admin" or changes.get("is_active") is False
        )
        if losing_admin and self._active_admins() <= 1:
            raise AccountError("Nie można odebrać uprawnień ostatniemu aktywnemu administratorowi.")

    def _active_admins(self) -> int:
        return int(
            self.db.fetch_value("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active")
            or 0
        )

    def delete_user(self, user_id: int, *, actor: Actor) -> None:
        user = self.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        self._guard_last_admin(user, {"is_active": False})
        self.db.execute("DELETE FROM users WHERE id = %s", [user_id])  # tokeny: ON DELETE CASCADE
        self.activity.record(
            "user.deleted",
            actor,
            subject_type="user",
            subject_id=user_id,
            details={"email": user.email, "role": user.role},
        )

    def change_password(self, user_id: int, *, current: str | None, new: str, actor: Actor) -> None:
        """Zmiana hasła unieważnia wszystkie tokeny (wylogowanie na innych urządzeniach).

        ``current=None`` — reset przez administratora (bez znajomości starego hasła).
        """
        row = self.db.fetch_one("SELECT email, password_hash FROM users WHERE id = %s", [user_id])
        if row is None:
            raise KeyError(user_id)
        if current is not None and not passwords.verify_password(current, row["password_hash"]):
            raise AuthenticationError("Obecne hasło jest nieprawidłowe.")
        try:
            passwords.validate(new, email=row["email"])
        except passwords.WeakPasswordError as exc:
            raise AccountError(str(exc)) from None
        self.db.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
            [passwords.hash_password(new), _iso(self.now()), user_id],
        )
        revoked = self.revoke_all_tokens(user_id)
        self.activity.record(
            "auth.password_changed" if current is not None else "auth.password_reset",
            actor,
            subject_type="user",
            subject_id=user_id,
            details={"revoked_tokens": revoked},
        )

    # --- logowanie ---------------------------------------------------------------------

    def login(
        self,
        email: str,
        password: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        token_name: str | None = None,
        ttl: timedelta = TOKEN_TTL,
        panel_only: bool = False,
    ) -> tuple[User, IssuedToken]:
        """Sprawdź hasło i wydaj token. Po 5 błędach w 15 min dla emaila — przerwa."""
        key = (email or "").strip().lower()[:255]
        since = _iso(self.now() - LOGIN_WINDOW)
        failures = self.activity.count_recent("auth.login_failed", key, since)
        if failures >= LOGIN_MAX_FAILURES:
            raise TooManyAttempts(int(LOGIN_WINDOW.total_seconds()))

        row = self.db.fetch_one(
            f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE lower(email) = %s", [key]
        )
        # porównanie hasła także dla nieistniejącego konta: stały czas odpowiedzi
        valid = passwords.verify_password(
            password or "", row["password_hash"] if row else passwords.DUMMY_HASH
        )
        allowed_role = row is not None and (
            not panel_only or row["role"] in permissions.PANEL_ROLES
        )
        if not (row and valid and row["is_active"] and allowed_role):
            reason = (
                "unknown_email"
                if row is None
                else "bad_password"
                if not valid
                else "inactive"
                if not row["is_active"]
                else "no_panel_role"
            )
            self.activity.record(
                "auth.login_failed",
                Actor(key or "anonim", row["id"] if row else None, ip, user_agent),
                subject_type="email",
                subject_id=key,
                details={"reason": reason},
            )
            raise AuthenticationError("Nieprawidłowy email lub hasło.")

        if passwords.needs_rehash(row["password_hash"]):
            self.db.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                [passwords.hash_password(password), row["id"]],
            )
        now = _iso(self.now())
        self.db.execute("UPDATE users SET last_login_at = %s WHERE id = %s", [now, row["id"]])
        user = User.from_row({**row, "last_login_at": now})
        issued = self.issue_token(user, name=token_name or "logowanie", ttl=ttl, log=False)
        self.activity.record(
            "auth.login",
            user.actor(ip, user_agent),
            subject_type="user",
            subject_id=user.id,
            details={"token_id": issued.access.id},
        )
        return user, issued

    # --- tokeny ------------------------------------------------------------------------

    def issue_token(
        self,
        user: User,
        *,
        name: str | None = None,
        abilities: Iterable[str] | None = None,
        ttl: timedelta | None = TOKEN_TTL,
        actor: Actor | None = None,
        log: bool = True,
    ) -> IssuedToken:
        if ttl is not None and not timedelta(minutes=1) <= ttl <= MAX_TOKEN_TTL:
            raise AccountError("Ważność tokenu: od 1 minuty do 90 dni.")
        try:
            granted = permissions.normalize_abilities(user.role, abilities)
        except ValueError as exc:
            raise AccountError(str(exc)) from None
        secret = tokens.new_secret()
        now = self.now()
        row = self.db.fetch_one(
            "INSERT INTO auth_access_tokens "
            "(tokenable_id, type, name, hash, abilities, created_at, updated_at, expires_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id, tokenable_id, name, abilities, created_at, last_used_at, expires_at",
            [
                user.id,
                tokens.TOKEN_TYPE,
                (name or "")[:255] or None,
                tokens.hash_secret(secret),
                json.dumps(granted),
                _iso(now),
                _iso(now),
                _iso(now + ttl) if ttl is not None else None,
            ],
        )
        access = _token_from_row(row)
        if log:
            self.activity.record(
                "auth.token_created",
                actor or user.actor(),
                subject_type="token",
                subject_id=access.id,
                details={
                    "name": access.name,
                    "abilities": granted,
                    "expires_at": access.expires_at,
                },
            )
        return IssuedToken(tokens.compose(access.id, secret), access)

    def authenticate(self, raw_token: str) -> Authenticated | None:
        """Sprawdź token z nagłówka; ``None`` = brak/zły/wygasły token lub nieaktywne konto."""
        parsed = tokens.parse(raw_token)
        if parsed is None:
            return None
        row = self.db.fetch_one(
            "SELECT t.id, t.tokenable_id, t.name, t.hash, t.abilities, t.created_at, "
            "t.last_used_at, t.expires_at, "
            "u.id AS u_id, u.name AS u_name, u.email AS u_email, u.role::text AS u_role, "
            "u.is_active AS u_active, u.created_at AS u_created, u.updated_at AS u_updated, "
            "u.last_login_at AS u_login "
            "FROM auth_access_tokens t JOIN users u ON u.id = t.tokenable_id "
            "WHERE t.id = %s AND t.type = %s",
            [parsed.token_id, tokens.TOKEN_TYPE],
        )
        if row is None or not tokens.matches(parsed.secret, row["hash"]):
            return None
        now = self.now()
        if row["expires_at"] and row["expires_at"] <= _iso(now):
            return None
        if not row["u_active"]:
            return None
        # last_used_at co najwyżej raz na minutę, żeby nie pisać przy każdym żądaniu
        if not row["last_used_at"] or row["last_used_at"] < _iso(now - timedelta(minutes=1)):
            self.db.execute(
                "UPDATE auth_access_tokens SET last_used_at = %s WHERE id = %s",
                [_iso(now), parsed.token_id],
            )
        user = User(
            id=row["u_id"],
            name=row["u_name"],
            email=row["u_email"],
            role=row["u_role"],
            is_active=row["u_active"],
            created_at=row["u_created"],
            updated_at=row["u_updated"],
            last_login_at=row["u_login"],
        )
        return Authenticated(user, _token_from_row(row))

    def list_tokens(self, user_id: int) -> list[AccessToken]:
        rows = self.db.fetch_all(
            "SELECT id, tokenable_id, name, abilities, created_at, last_used_at, expires_at "
            "FROM auth_access_tokens WHERE tokenable_id = %s AND type = %s "
            "AND (expires_at IS NULL OR expires_at > %s) ORDER BY created_at DESC",
            [user_id, tokens.TOKEN_TYPE, _iso(self.now())],
        )
        return [_token_from_row(row) for row in rows]

    def revoke_token(self, token_id: int, *, user_id: int | None = None, actor: Actor) -> bool:
        params: list[Any] = [token_id]
        owner = ""
        if user_id is not None:
            owner = " AND tokenable_id = %s"
            params.append(user_id)
        deleted = self.db.execute(f"DELETE FROM auth_access_tokens WHERE id = %s{owner}", params)
        if deleted:
            self.activity.record(
                "auth.token_revoked", actor, subject_type="token", subject_id=token_id
            )
        return bool(deleted)

    def revoke_all_tokens(self, user_id: int) -> int:
        return self.db.execute("DELETE FROM auth_access_tokens WHERE tokenable_id = %s", [user_id])

    def purge_expired_tokens(self) -> int:
        return self.db.execute(
            "DELETE FROM auth_access_tokens WHERE expires_at IS NOT NULL AND expires_at <= %s",
            [_iso(self.now())],
        )
