"""Category-to-client registry for the high-level reader."""

import os

from .base import BaseApiClient
from .clients import CLIENT_CLASSES
from .models import Category

CLIENTS_BY_CATEGORY: dict[Category, tuple[type[BaseApiClient], ...]] = {
    category: tuple(
        client_class
        for client_class in CLIENT_CLASSES
        if category in client_class.supported_categories
    )
    for category in Category
}


DISABLED_CLIENTS_ENV = "API_READING_DISABLED_CLIENTS"


def disabled_client_names() -> frozenset[str]:
    """Clients switched off by the admin panel (comma-separated names in the environment)."""

    raw = os.getenv(DISABLED_CLIENTS_ENV, "")
    return frozenset(name.strip().lower() for name in raw.split(",") if name.strip())


def clients_for_categories(
    categories: list[Category],
) -> tuple[list[type[BaseApiClient]], list[Category]]:
    """Return each matching client once and categories with no registered source.

    Clients disabled via ``API_READING_DISABLED_CLIENTS`` are skipped; a category whose
    every client is disabled is reported as having no source.
    """

    disabled = disabled_client_names()
    selected: list[type[BaseApiClient]] = []
    without_source: list[Category] = []
    for category in categories:
        matching_clients = tuple(
            client_class
            for client_class in CLIENTS_BY_CATEGORY.get(category, ())
            if client_class.name not in disabled
        )
        if not matching_clients:
            without_source.append(category)
            continue
        for client_class in matching_clients:
            if client_class not in selected:
                selected.append(client_class)
    return selected, without_source
