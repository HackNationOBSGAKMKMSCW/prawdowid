"""HTTP: logowanie, konta, lista stron zaufanych i dziennik działań.

* ``create_auth_router(prefix)`` — ``/login``, ``/logout``, ``/me``, ``/me/password``,
  ``/me/tokens`` (dla panelu pod ``/api/admin/auth``, dla serwisu pod ``/api/auth``
  razem z ``/register`` i ``/me/queries``).
* ``create_management_router()`` — konta (``/accounts``), źródła (``/sources``) i dziennik
  działań (``/activity``) dla panelu admina.

``Guard`` sprawdza token z nagłówka ``Authorization: Bearer`` i uprawnienie roli. Stały
``ADMIN_API_TOKEN`` działa nadal jako awaryjny dostęp administratora (np. przed
utworzeniem pierwszego konta).
"""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from . import permissions
from .activity import ActivityLog, Actor
from .service import (
    AccountError,
    AccountService,
    AuthenticationError,
    TooManyAttempts,
    User,
)
from .trusted import SourceError, TrustedSourceRepository

# Konta zakłada administrator w panelu; tylko role panelu (konta „user” nie mają dostępu).
Role = Literal["analyst", "admin"]


@dataclass(frozen=True)
class Principal:
    """Kto wywołuje endpoint: konto z tokenem albo awaryjny token serwisowy."""

    label: str
    role: str
    user: User | None
    token_id: int | None
    abilities: tuple[str, ...]
    ip: str | None = None
    user_agent: str | None = None

    def can(self, permission: str) -> bool:
        return permissions.allowed(self.role, self.abilities, permission)

    def actor(self) -> Actor:
        return Actor(self.label, self.user.id if self.user else None, self.ip, self.user_agent)


def _client(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


class Guard:
    def __init__(
        self,
        accounts: AccountService | None,
        service_token: str | None = None,
        *,
        panel_only: bool = True,
    ) -> None:
        self.accounts = accounts
        self.service_token = service_token
        self.panel_only = panel_only

    @property
    def enabled(self) -> bool:
        return bool(self.accounts or self.service_token)

    def principal(
        self,
        request: Request,
        authorization: str | None,
        x_admin_user: str | None = None,
    ) -> Principal:
        if not self.enabled:
            raise HTTPException(
                503, "Panel admina jest wyłączony: ustaw DATABASE_URL albo ADMIN_API_TOKEN."
            )
        ip, agent = _client(request)
        scheme, _, token = (authorization or "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Zaloguj się.")
        if self.service_token and hmac.compare_digest(token.encode(), self.service_token.encode()):
            label = (x_admin_user or "admin").strip()[:64] or "admin"
            return Principal(label, "admin", None, None, ("*",), ip, agent)
        if self.accounts is None:
            raise HTTPException(401, "Nieprawidłowy token.")
        auth = self.accounts.authenticate(token)
        if auth is None:
            raise HTTPException(401, "Sesja wygasła albo token jest nieprawidłowy.")
        if self.panel_only and auth.user.role not in permissions.PANEL_ROLES:
            raise HTTPException(403, "To konto nie ma dostępu do panelu.")
        return Principal(
            auth.user.email,
            auth.user.role,
            auth.user,
            auth.token.id,
            tuple(auth.token.abilities),
            ip,
            agent,
        )

    def require(self, permission: str | None = None) -> Callable[..., Principal]:
        def dependency(
            request: Request,
            authorization: str | None = Header(default=None),
            x_admin_user: str | None = Header(default=None),
        ) -> Principal:
            principal = self.principal(request, authorization, x_admin_user)
            if permission and not principal.can(permission):
                raise HTTPException(403, "Brak uprawnień do tej operacji.")
            return principal

        return dependency


# --- modele żądań ----------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)


class PasswordChange(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


class TokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    abilities: list[str] | None = None
    days: int = Field(default=30, ge=1, le=90)


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255)
    password: str = Field(max_length=256)
    role: Role = "analyst"


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    role: Role | None = None
    active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(max_length=256)


class SourceCreate(BaseModel):
    url: str = Field(max_length=2000)
    name: str = Field(min_length=1, max_length=200)
    topics: list[str] = Field(default_factory=list)
    description: str = ""
    adapter: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    topics: list[str] | None = None
    description: str | None = None
    adapter: str | None = None
    params: dict[str, Any] | None = None
    enabled: bool | None = None


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(422, str(exc))


def _session(user: User, issued: Any) -> dict[str, Any]:
    """Kształt ``Session`` z kontraktu panelu."""
    return {
        "token": issued.token,
        "user": user.public(),
        "expiresAt": issued.access.expires_at,
        "abilities": issued.access.abilities,
    }


# --- logowanie -------------------------------------------------------------------------


def create_auth_router(
    accounts: AccountService,
    *,
    prefix: str,
    panel: bool,
    allow_registration: bool = False,
    query_journal: Callable[[int, int, int], dict[str, Any]] | None = None,
) -> APIRouter:
    """``panel=True``: logować się mogą tylko role panelu; bez rejestracji."""
    router = APIRouter(prefix=prefix, tags=["auth"])
    guard = Guard(accounts, panel_only=panel)
    signed_in = guard.require()

    @router.post("/login")
    def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        ip, agent = _client(request)
        try:
            user, issued = accounts.login(
                body.email,
                body.password,
                ip=ip,
                user_agent=agent,
                token_name="panel" if panel else "serwis",
                panel_only=panel,
            )
        except TooManyAttempts as exc:
            response.headers["Retry-After"] = str(exc.retry_after)
            raise HTTPException(
                429,
                "Za dużo nieudanych prób logowania. Spróbuj ponownie za kilkanaście minut.",
                headers={"Retry-After": str(exc.retry_after)},
            ) from None
        except AuthenticationError:
            raise HTTPException(401, "Nieprawidłowy email lub hasło.") from None
        return _session(user, issued)

    @router.post("/logout", status_code=204)
    def logout(principal: Principal = Depends(signed_in)) -> Response:
        if principal.token_id is not None:
            accounts.revoke_token(principal.token_id, actor=principal.actor())
            accounts.activity.record(
                "auth.logout",
                principal.actor(),
                subject_type="user",
                subject_id=principal.user.id if principal.user else None,
            )
        return Response(status_code=204)

    @router.get("/me")
    def me(principal: Principal = Depends(signed_in)) -> dict[str, Any]:
        if principal.user is None:  # awaryjny token serwisowy
            return {
                "id": "service-token",
                "email": "",
                "name": principal.label,
                "role": "admin",
                "active": True,
                "createdAt": None,
                "lastLoginAt": None,
            }
        return {
            **principal.user.public(),
            "permissions": sorted(permissions.role_permissions(principal.role)),
        }

    def own(principal: Principal) -> User:
        if principal.user is None:
            raise HTTPException(400, "Token serwisowy nie jest kontem.")
        return principal.user

    @router.post("/me/password", status_code=204)
    def change_password(
        body: PasswordChange, principal: Principal = Depends(signed_in)
    ) -> Response:
        user = own(principal)
        try:
            accounts.change_password(
                user.id, current=body.current, new=body.new, actor=principal.actor()
            )
        except AuthenticationError as exc:
            raise HTTPException(403, str(exc)) from None
        except AccountError as exc:
            raise _bad_request(exc) from None
        return Response(status_code=204)

    @router.get("/me/tokens")
    def my_tokens(principal: Principal = Depends(signed_in)) -> list[dict[str, Any]]:
        return [token.public() for token in accounts.list_tokens(own(principal).id)]

    @router.post("/me/tokens")
    def new_token(body: TokenRequest, principal: Principal = Depends(signed_in)) -> dict[str, Any]:
        """Token do integracji (np. skrypt); sekret jest pokazywany tylko raz."""
        try:
            issued = accounts.issue_token(
                own(principal),
                name=body.name,
                abilities=body.abilities,
                ttl=timedelta(days=body.days),
                actor=principal.actor(),
            )
        except AccountError as exc:
            raise _bad_request(exc) from None
        return {"token": issued.token, **issued.access.public()}

    @router.delete("/me/tokens/{token_id}", status_code=204)
    def revoke(token_id: int, principal: Principal = Depends(signed_in)) -> Response:
        if not accounts.revoke_token(token_id, user_id=own(principal).id, actor=principal.actor()):
            raise HTTPException(404, "Nie znaleziono tokenu.")
        return Response(status_code=204)

    if allow_registration:

        @router.post("/register", status_code=201)
        def register(body: RegisterRequest, request: Request) -> dict[str, Any]:
            ip, agent = _client(request)
            try:
                user = accounts.create_user(
                    name=body.name,
                    email=body.email,
                    password=body.password,
                    role="user",
                    actor=Actor(body.email.strip().lower()[:255], None, ip, agent),
                )
            except AccountError as exc:
                raise _bad_request(exc) from None
            _, issued = accounts.login(body.email, body.password, ip=ip, user_agent=agent)
            return _session(user, issued)

    if query_journal is not None:

        @router.get("/me/queries")
        def my_queries(
            limit: int = Query(50, ge=1, le=200),
            offset: int = Query(0, ge=0),
            principal: Principal = Depends(guard.require("me:read")),
        ) -> dict[str, Any]:
            """Historia własnych zapytań (dziennik zapytań powiązany z kontem)."""
            return query_journal(own(principal).id, limit, offset)

    return router


# --- zarządzanie: konta, źródła, dziennik ---------------------------------------------


def create_management_router(
    guard: Guard,
    accounts: AccountService,
    sources: TrustedSourceRepository,
    activity: ActivityLog,
    *,
    prefix: str = "/api/admin",
    on_sources_changed: Callable[[], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix)

    def account_or_404(user_id: int) -> User:
        user = accounts.get_user(user_id)
        if user is None:
            raise HTTPException(404, f"Nie znaleziono konta {user_id}.")
        return user

    @router.get("/accounts", tags=["accounts"])
    def list_accounts(
        role: Role | None = None,
        active: bool | None = None,
        q: str | None = Query(None, max_length=100),
        _: Principal = Depends(guard.require("users:read")),
    ) -> list[dict[str, Any]]:
        return [user.public() for user in accounts.list_users(role=role, active=active, search=q)]

    @router.post("/accounts", tags=["accounts"])
    def create_account(
        body: AccountCreate, principal: Principal = Depends(guard.require("users:write"))
    ) -> dict[str, Any]:
        try:
            user = accounts.create_user(
                name=body.name,
                email=body.email,
                password=body.password,
                role=body.role,
                actor=principal.actor(),
            )
        except AccountError as exc:
            raise _bad_request(exc) from None
        return user.public()

    @router.patch("/accounts/{user_id}", tags=["accounts"])
    def update_account(
        user_id: int,
        body: AccountUpdate,
        principal: Principal = Depends(guard.require("users:write")),
    ) -> dict[str, Any]:
        account_or_404(user_id)
        if principal.user and principal.user.id == user_id and body.role not in (None, "admin"):
            raise HTTPException(422, "Nie możesz odebrać sobie roli administratora.")
        try:
            user = accounts.update_user(
                user_id,
                actor=principal.actor(),
                name=body.name,
                role=body.role,
                active=body.active,
            )
        except AccountError as exc:
            raise _bad_request(exc) from None
        return user.public()

    @router.post("/accounts/{user_id}/password", status_code=204, tags=["accounts"])
    def reset_password(
        user_id: int,
        body: PasswordReset,
        principal: Principal = Depends(guard.require("users:write")),
    ) -> Response:
        account_or_404(user_id)
        try:
            accounts.change_password(
                user_id, current=None, new=body.password, actor=principal.actor()
            )
        except AccountError as exc:
            raise _bad_request(exc) from None
        return Response(status_code=204)

    @router.delete("/accounts/{user_id}", status_code=204, tags=["accounts"])
    def delete_account(
        user_id: int, principal: Principal = Depends(guard.require("users:write"))
    ) -> Response:
        account_or_404(user_id)
        if principal.user and principal.user.id == user_id:
            raise HTTPException(422, "Nie możesz usunąć własnego konta.")
        try:
            accounts.delete_user(user_id, actor=principal.actor())
        except AccountError as exc:
            raise _bad_request(exc) from None
        return Response(status_code=204)

    # --- strony zaufane ---------------------------------------------------------------

    def changed() -> None:
        if on_sources_changed is not None:
            on_sources_changed()

    @router.get("/sources", tags=["sources"])
    def list_sources(
        enabled_only: bool = False, _: Principal = Depends(guard.require("sources:read"))
    ) -> list[dict[str, Any]]:
        return sources.list(enabled_only=enabled_only)

    @router.post("/sources", tags=["sources"])
    def create_source(
        body: SourceCreate, principal: Principal = Depends(guard.require("sources:write"))
    ) -> dict[str, Any]:
        try:
            source = sources.create(
                body.url, body.model_dump(exclude={"url"}), actor=principal.actor()
            )
        except SourceError as exc:
            raise _bad_request(exc) from None
        changed()
        return source

    @router.patch("/sources", tags=["sources"])
    def update_source(
        body: SourceUpdate,
        url: str = Query(..., max_length=2000, description="adres źródła (klucz)"),
        principal: Principal = Depends(guard.require("sources:write")),
    ) -> dict[str, Any]:
        try:
            source = sources.update(
                url, body.model_dump(exclude_unset=True), actor=principal.actor()
            )
        except KeyError:
            raise HTTPException(404, "Nie znaleziono źródła.") from None
        except SourceError as exc:
            raise _bad_request(exc) from None
        changed()
        return source

    @router.delete("/sources", status_code=204, tags=["sources"])
    def delete_source(
        url: str = Query(..., max_length=2000),
        principal: Principal = Depends(guard.require("sources:write")),
    ) -> Response:
        try:
            sources.delete(url, actor=principal.actor())
        except KeyError:
            raise HTTPException(404, "Nie znaleziono źródła.") from None
        changed()
        return Response(status_code=204)

    @router.post("/sources/seed", tags=["sources"])
    def seed_sources(
        principal: Principal = Depends(guard.require("sources:write")),
    ) -> dict[str, Any]:
        """Wgraj listę z ``trustedSources/whitelist.py`` (istniejących wpisów nie zmienia)."""
        from trustedSources.whitelist import WHITELIST

        added = sources.seed(WHITELIST, actor=principal.actor())
        changed()
        return {"added": added, "total": len(sources.list())}

    # --- dziennik działań -------------------------------------------------------------

    @router.get("/activity", tags=["activity"])
    def list_activity(
        action: str | None = Query(None, max_length=100, description="np. auth.login albo auth."),
        user_id: int | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        _: Principal = Depends(guard.require("audit:read")),
    ) -> dict[str, Any]:
        items, total = activity.list(
            action=action,
            user_id=user_id,
            subject_type=subject_type,
            subject_id=subject_id,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    return router


def registration_enabled() -> bool:
    return os.getenv("ACCOUNTS_REGISTRATION", "open").strip().lower() not in {"0", "off", "closed"}


def create_service_router(database: Any, *, allow_registration: bool | None = None) -> APIRouter:
    """``/api/auth`` dla użytkowników serwisu: rejestracja, logowanie, historia zapytań.

    Podpięcie w aplikacji serwisu: ``app.include_router(create_service_router(get_database()))``.
    Zapytanie zalogowanego trafia do dziennika z ``account_id``
    (``monitor.screen(..., account_id=user.id)``) i jest widoczne w ``/api/auth/me/queries``.
    """
    from admin.store import PostgresAdminStore

    store = PostgresAdminStore(database)
    accounts = AccountService(database)

    def journal(user_id: int, limit: int, offset: int) -> dict[str, Any]:
        items, total = store.list_queries(account_id=user_id, limit=limit, offset=offset)
        visible = ("id", "ts", "channel", "text", "status", "verdict", "flags", "completed_at")
        return {
            "total": total,
            "items": [{key: item.get(key) for key in visible} for item in items],
        }

    return create_auth_router(
        accounts,
        prefix="/api/auth",
        panel=False,
        allow_registration=registration_enabled()
        if allow_registration is None
        else allow_registration,
        query_journal=journal,
    )
