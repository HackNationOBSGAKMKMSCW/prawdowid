from datetime import UTC, datetime

import pytest

from trustedSources.cache import CACHE
from trustedSources.models import TrustedSource
from trustedSources.registry import SourceRegistry
from trustedSources.store import StaticSourceStore
from trustedSources.whitelist import WhitelistEntry


@pytest.fixture(autouse=True)
def _clean_cache():
    CACHE.clear()
    yield
    CACHE.clear()


ENTRIES = (
    WhitelistEntry("https://www.gov.pl/web/rcb/raport-dobowy3", "RCB"),
    WhitelistEntry("https://demagog.org.pl/", "Demagog"),
    WhitelistEntry("https://policja.pl/pol/aktualnosci", "Policja"),
    WhitelistEntry("https://meteo.imgw.pl/", "IMGW", topics=("pogoda", "silny wiatr"), adapter="reference"),
)


@pytest.fixture
def registry() -> SourceRegistry:
    return SourceRegistry(store=StaticSourceStore(ENTRIES))


def make_source(**overrides) -> TrustedSource:
    values = {
        "id": "src",
        "url": "https://example.gov.pl/aktualnosci",
        "name": "Example",
        "adapter": "listing",
        "domains": ["example.gov.pl"],
        "path_prefix": "/aktualnosci",
        "added_at": datetime(2026, 11, 1, tzinfo=UTC),
    }
    values.update(overrides)
    return TrustedSource(**values)
