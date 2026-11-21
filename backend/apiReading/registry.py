"""Category-to-client registry for the high-level reader."""

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


def clients_for_categories(
    categories: list[Category],
) -> tuple[list[type[BaseApiClient]], list[Category]]:
    """Return each matching client once and categories with no registered source."""

    selected: list[type[BaseApiClient]] = []
    without_source: list[Category] = []
    for category in categories:
        matching_clients = CLIENTS_BY_CATEGORY.get(category, ())
        if not matching_clients:
            without_source.append(category)
            continue
        for client_class in matching_clients:
            if client_class not in selected:
                selected.append(client_class)
    return selected, without_source
