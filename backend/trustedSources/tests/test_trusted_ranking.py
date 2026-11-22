from datetime import UTC, datetime

from trustedSources.models import EvidenceHit
from trustedSources.ranking import rank_hits
from trustedSources.text import fold, stems

from .conftest import make_source


def hit(title: str, url: str, source_id: str = "gov", **extra) -> EvidenceHit:
    return EvidenceHit(source_id=source_id, source_name=source_id, url=url, title=title, **extra)


def test_fold_and_stems_merge_polish_inflections() -> None:
    assert fold("Płaska ŻÓŁTA") == "plaska zolta"
    assert stems("płaska Ziemia") == stems("płaskiej ziemi")
    assert stems("szczepionki autyzm") == stems("szczepień autyzmu")
    assert stems("szczepionki") != stems("Szczecinie")
    assert stems("szczepionki") != stems("Szczepańskiego")
    assert stems("czy 5G jest groźne") == ["5g", "grozn"]


def test_two_word_query_requires_both_words() -> None:
    sources = {"gov": make_source(id="gov", domains=["www.gov.pl"])}
    hits = [
        hit("Poprawa jakości wody - Wodociąg Płaska", "https://www.gov.pl/web/psse/wodociag-plaska"),
        hit("Ziemia jest płaska? To mit", "https://www.gov.pl/web/nauka/plaska-ziemia-mit"),
    ]
    ranked = rank_hits(hits, ["płaska Ziemia"], sources)
    assert [item.title for item in ranked] == ["Ziemia jest płaska? To mit"]
    assert ranked[0].query == "płaska Ziemia"


def test_off_domain_urls_and_duplicates_are_dropped() -> None:
    sources = {"gov": make_source(id="gov", domains=["www.gov.pl"])}
    hits = [
        hit("Alert RCB silny wiatr", "https://www.gov.pl/web/rcb/alert#top"),
        hit("Alert RCB silny wiatr (kopia)", "https://www.gov.pl/web/rcb/alert"),
        hit("Alert RCB silny wiatr", "https://evil.example/gov.pl/alert"),
        hit("Alert RCB silny wiatr", "https://www.gov.pl.evil.example/alert"),
    ]
    ranked = rank_hits(hits, ["alert RCB silny wiatr"], sources)
    assert [item.url for item in ranked] == ["https://www.gov.pl/web/rcb/alert"]


def test_limits_per_source_and_total() -> None:
    sources = {name: make_source(id=name, domains=["example.pl"]) for name in ("a", "b")}
    hits = [
        hit(f"Ostrzeżenie: powódź {index}", f"https://example.pl/{name}/{index}", source_id=name)
        for name in ("a", "b")
        for index in range(5)
    ]
    ranked = rank_hits(hits, ["powódź"], sources, max_hits=4, max_hits_per_source=3)
    assert len(ranked) == 4
    assert sum(1 for item in ranked if item.source_id == "a") <= 3


def test_relaxed_sources_and_fact_checker_bonus() -> None:
    sources = {
        "fc": make_source(id="fc", domains=["demagog.org.pl"], trust="fact_checker"),
        "gov": make_source(id="gov", domains=["www.gov.pl"]),
    }
    hits = [
        hit("Szczepionki a autyzm", "https://demagog.org.pl/fake_news/x", "fc", trust="fact_checker"),
        hit("Szczepienia ochronne", "https://www.gov.pl/web/gis/szczepienia"),
    ]
    ranked = rank_hits(hits, ["szczepionki autyzm"], sources, relaxed_sources=frozenset({"fc"}))
    assert [item.source_id for item in ranked] == ["fc"]


def test_recent_hits_rank_higher_when_equally_relevant() -> None:
    sources = {"gov": make_source(id="gov", domains=["www.gov.pl"])}
    now = datetime(2026, 11, 22, tzinfo=UTC)
    hits = [
        hit("Alert RCB silny wiatr", "https://www.gov.pl/web/rcb/old", published_at=datetime(2020, 1, 1, tzinfo=UTC)),
        hit("Alert RCB silny wiatr", "https://www.gov.pl/web/rcb/new", published_at=datetime(2026, 11, 20, tzinfo=UTC)),
    ]
    ranked = rank_hits(hits, ["alert RCB silny wiatr"], sources, now=now)
    assert ranked[0].url.endswith("/new")


def test_reference_hits_match_on_topics_with_relaxed_coverage() -> None:
    sources = {"imgw": make_source(id="imgw", url="https://meteo.imgw.pl/", domains=["meteo.imgw.pl"])}
    hits = [
        EvidenceHit(
            source_id="imgw",
            source_name="IMGW",
            url="https://meteo.imgw.pl/",
            title="IMGW",
            snippet="pogoda, silny wiatr",
            kind="reference",
        )
    ]
    assert rank_hits(hits, ["wichura silny wiatr Kraków"], sources)
    assert not rank_hits(hits, ["szczepionki autyzm"], sources)


def test_long_query_needs_half_and_same_titles_are_merged() -> None:
    sources = {"a": make_source(id="a", domains=["example.gov.pl"]), "b": make_source(id="b", domains=["example.gov.pl"])}
    hits = [
        EvidenceHit(source_id="a", source_name="A", url="https://example.gov.pl/aktualnosci/1",
                    title="Szczepienie przeciw COVID-19 obowiązkowe"),
        EvidenceHit(source_id="b", source_name="B", url="https://example.gov.pl/aktualnosci/2",
                    title="Szczepienie przeciw COVID-19 obowiązkowe"),
        EvidenceHit(source_id="a", source_name="A", url="https://example.gov.pl/aktualnosci/3",
                    title="Nowe przepisy dla kierowców"),
    ]
    ranked = rank_hits(hits, ["Rząd wprowadza obowiązkowe szczepienia na COVID dla wszystkich"], sources)
    assert [hit.url for hit in ranked] == ["https://example.gov.pl/aktualnosci/1"]
