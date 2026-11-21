from types import SimpleNamespace

from prawdowid_analysis.adapters import (
    claims_from_analysis,
    reading_errors,
    sources_from_reading_results,
)

FC_CLAIM = {
    "text": "Szczepionki zawierają mikroczipy",
    "claimant": "Post w mediach społecznościowych",
    "claimDate": "2021-03-01T00:00:00Z",
    "claimReview": [
        {
            "publisher": {"name": "Demagog", "site": "demagog.org.pl"},
            "url": "https://demagog.org.pl/fake_news/mikroczipy",
            "title": "Szczepionki nie zawierają mikroczipów",
            "reviewDate": "2021-03-05T10:00:00Z",
            "textualRating": "Fałsz",
            "languageCode": "pl",
        },
        {"publisher": {"name": "Bez oceny"}, "url": "https://x.example", "title": "t"},
    ],
}


def _reading_result(query, items, errors=()):
    return SimpleNamespace(
        request=SimpleNamespace(query=query),
        items=[SimpleNamespace(id="1", source="google_fact_check", payload=p) for p in items],
        results=[SimpleNamespace(source=s, error=e, result=None) for s, e in errors],
    )


def test_claims_from_analysis_reads_container_fields():
    analysis = SimpleNamespace(
        statements=["  Pierwsze  stwierdzenie. ", "", "Drugie."],
        security_warnings=["ostrzeżenie"],
        language_code="pl",
        category="Zdrowie i Medycyna",
    )
    claims = claims_from_analysis(analysis)
    assert claims.statements == ["Pierwsze stwierdzenie.", "Drugie."]
    assert claims.warnings == ["ostrzeżenie"]
    assert claims.language_code == "pl"


def test_claims_from_analysis_accepts_dict():
    claims = claims_from_analysis({"statements": ["A."], "security_warnings": []})
    assert claims.statements == ["A."]


def test_fact_check_review_becomes_reference_source():
    grouped = sources_from_reading_results([_reading_result("Szczepionki mają czipy", [FC_CLAIM])])
    sources = grouped["Szczepionki mają czipy"]
    assert len(sources) == 1, "recenzja bez oceny jest pomijana"
    source = sources[0]
    assert source.kind == "fact_check"
    assert source.source_id.startswith("FC-")
    assert source.publisher == "Demagog"
    assert source.rating == "Fałsz"
    assert source.published_at == "2021-03-05"
    assert "Ocena fact-checkera: Fałsz" in source.text
    assert "Sprawdzane twierdzenie: Szczepionki zawierają mikroczipy" in source.text


def test_source_ids_are_stable_and_deduplicated():
    first = sources_from_reading_results([_reading_result("q", [FC_CLAIM, FC_CLAIM])])["q"]
    second = sources_from_reading_results([_reading_result("q", [FC_CLAIM])])["q"]
    assert [s.source_id for s in first] == [s.source_id for s in second]


def test_reading_errors_are_reported():
    error = RuntimeError("boom")
    errors = reading_errors([_reading_result("q", [], errors=[("google_fact_check", error)])])
    assert errors == ["Źródło google_fact_check: RuntimeError"]
