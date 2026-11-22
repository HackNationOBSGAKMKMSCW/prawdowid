import pytest

from trustedSources.models import LastCheck
from trustedSources.registry import SourceNotFoundError, SourceRegistry, canonical_source_url
from trustedSources.store import StaticSourceStore
from trustedSources.whitelist import WHITELIST, WhitelistEntry


def test_registry_classifies_entries_without_network(registry: SourceRegistry) -> None:
    sources = {source.name: source for source in registry.list()}
    assert sources["RCB"].adapter == "govpl_search"
    assert sources["RCB"].params == {"site_id": "rcb"}
    assert sources["RCB"].domains == ["www.gov.pl"]
    assert sources["Demagog"].adapter == "fact_check_publisher"
    assert sources["Demagog"].trust == "fact_checker"
    assert sources["Policja"].adapter == "pending"
    assert sources["Policja"].path_prefix == "/pol/aktualnosci"
    assert sources["IMGW"].adapter == "reference" and sources["IMGW"].adapter_locked
    with pytest.raises(SourceNotFoundError):
        registry.get("nope")


def test_hardcoded_whitelist_is_valid_and_has_no_portal_wide_govpl() -> None:
    sources = SourceRegistry().list()
    assert len(sources) == len({canonical_source_url(entry.url) for entry in WHITELIST})
    govpl = [source for source in sources if source.adapter == "govpl_search"]
    assert govpl and all(source.params.get("site_id") for source in govpl)
    assert any(source.adapter == "fact_check_publisher" for source in sources)


def test_invalid_duplicate_and_disabled_entries() -> None:
    store = StaticSourceStore(
        (
            WhitelistEntry("https://moje.cert.pl/komunikaty/#lista", "CERT"),
            WhitelistEntry("https://MOJE.cert.pl/komunikaty/", "CERT duplikat"),
            WhitelistEntry("http://localhost/", "lokalny"),
            WhitelistEntry("https://kgsok.pl/", "KGSOK", enabled=False),
        )
    )
    registry = SourceRegistry(store=store)
    assert [source.name for source in registry.list()] == ["CERT", "KGSOK"]
    assert registry.list()[0].url == "https://moje.cert.pl/komunikaty/"
    assert [source.name for source in registry.list(enabled_only=True)] == ["CERT"]


def test_detection_results_survive_reload_from_store(registry: SourceRegistry) -> None:
    policja = next(source for source in registry.list() if source.name == "Policja")
    check = LastCheck(at=policja.added_at, ok=True, detail="feed")
    registry.save(
        policja.model_copy(update={"adapter": "feed", "params": {"feed_url": "x"}, "last_check": check})
    )
    registry.refresh()
    reloaded = registry.get(policja.id)
    assert reloaded.adapter == "feed" and reloaded.params == {"feed_url": "x"}
    assert reloaded.last_check == check


def test_store_changes_are_picked_up_after_refresh_interval() -> None:
    entries = [WhitelistEntry("https://kgsok.pl/", "KGSOK")]

    class MutableStore:
        def load(self):
            return list(entries)

    registry = SourceRegistry(store=MutableStore(), refresh_seconds=0)
    assert len(registry.list()) == 1
    entries.append(WhitelistEntry("https://www.sar.gov.pl/", "SAR"))
    assert len(registry.list()) == 2
