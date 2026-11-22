"""Role i uprawnienia — te same co w panelu (``admin_panel/frontend/src/auth/permissions.ts``).

Panel tylko chowa przyciski; backend egzekwuje uprawnienia przy każdym żądaniu.
Token może mieć węższy zakres niż rola (``abilities``), nigdy szerszy.
"""

from __future__ import annotations

from collections.abc import Iterable

ROLES = ("user", "moderator", "analyst", "admin")
PANEL_ROLES = ("moderator", "analyst", "admin")

_COMMON = frozenset(
    {
        "dashboard:read",
        "alerts:read",
        "alerts:write",
        "clusters:read",
        "cases:read",
        "cases:write",
        "cases:forward",
        "checks:read",
        "sources:read",
        "security:read",
        "rules:read",
        "endusers:read",
        "export",
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "user": frozenset({"checks:create", "me:read", "me:write"}),
    "moderator": _COMMON | {"endusers:write", "me:read", "me:write"},
    "analyst": _COMMON | {"sources:write", "models:read", "settings:read", "me:read", "me:write"},
    "admin": _COMMON
    | {
        "checks:delete",
        "sources:write",
        "models:read",
        "models:write",
        "channels:write",
        "rules:write",
        "settings:read",
        "settings:write",
        "users:read",
        "users:write",
        "audit:read",
        "endusers:write",
        "me:read",
        "me:write",
    },
}

ALL = "*"


def role_permissions(role: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def allowed(role: str, abilities: Iterable[str], permission: str) -> bool:
    """Rola musi dawać uprawnienie, a token musi je obejmować (``*`` albo ``obszar:*``)."""
    if permission not in role_permissions(role):
        return False
    granted = set(abilities)
    area = permission.split(":", 1)[0]
    return bool(granted & {ALL, permission, f"{area}:*"})


def normalize_abilities(role: str, abilities: Iterable[str] | None) -> list[str]:
    """Zakres nowego tokenu: domyślnie wszystko, na co pozwala rola; nieznane odrzuca."""
    if abilities is None:
        return [ALL]
    requested = sorted({ability.strip() for ability in abilities if ability.strip()})
    permitted = role_permissions(role)
    unknown = [
        ability
        for ability in requested
        if ability != ALL
        and ability not in permitted
        and not any(p.startswith(ability[:-1]) for p in permitted if ability.endswith(":*"))
    ]
    if unknown:
        raise ValueError(f"rola {role} nie daje uprawnień: {', '.join(unknown)}")
    return requested or [ALL]
