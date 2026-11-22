import json

from prawdowid_analysis.output import compact
from prawdowid_analysis.schemas import (
    ClaimVerdict,
    EvidenceOut,
    InputSourceOut,
    ReferenceSource,
    SourceFreshness,
    SourceReviewOut,
    TextVerdict,
)


def sample() -> TextVerdict:
    corpus = ReferenceSource(
        source_id="KOR-1",
        kind="korpus",
        title="Akcesja",
        publisher="Wydawca",
        published_at="2026-11-21",
        fetched_at="2026-11-21T00:00:00Z",
        text="Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku.",
    )
    user = ReferenceSource(
        source_id="UZ-1",
        kind="uzytkownik",
        title="Relacja",
        publisher="Gazeta",
        url="https://przyklad.pl/relacja",
        published_at="2010-01-01",
        text="Bardzo długa treść źródła użytkownika.",
    )
    claim = ClaimVerdict(
        claim_id="T1",
        claim="Polska weszła do UE w 2004 roku.",
        verdict="prawda",
        verdict_label="Prawda",
        confidence="wysoka",
        claim_interpretation="Data akcesji.",
        explanation="Źródło [KOR-1] podaje datę.",
        reasoning_steps=["[KOR-1] podaje 1 maja 2004."],
        evidence=[
            EvidenceOut(
                source_id="KOR-1",
                quote="Polska przystąpiła do Unii Europejskiej 1 maja 2004 roku",
                stance="potwierdza",
                quote_verified=True,
                source_title="Akcesja",
                publisher="Wydawca",
                url=None,
                published_at="2026-11-21",
                fetched_at="2026-11-21T00:00:00Z",
                age_days=-8000,
            )
        ],
        sources_reviewed=[
            SourceReviewOut(
                source_id="KOR-1",
                relevant=True,
                why="Podaje datę",
                title="Akcesja",
                publisher="Wydawca",
                published_at="2026-11-21",
            ),
            SourceReviewOut(
                source_id="UZ-1",
                relevant=False,
                why="Inny temat",
                title="Relacja",
                url="https://przyklad.pl/relacja",
            ),
        ],
        source_freshness=[
            SourceFreshness(source_id="KOR-1", published_at="2026-11-21", age_days=-8000),
            SourceFreshness(
                source_id="UZ-1",
                published_at="2010-01-01",
                age_days=5478,
                freshness_flags=["material_archiwalny"],
            ),
        ],
        model_verdict="prawda",
        source_ids=["KOR-1", "UZ-1"],
        context="Tekst użytkownika.",
        model="m",
    )
    return TextVerdict(
        verdict="prawdziwy",
        summary="Sprawdzono 1 twierdzenie: 1 – prawda.",
        claims=[claim],
        sources=[corpus, user],
        input_sources=[
            InputSourceOut(
                source_id="UZ-1",
                kind="uzytkownik",
                title="Relacja",
                publisher="Gazeta",
                url="https://przyklad.pl/relacja",
                published_at="2010-01-01",
                status="pokazane_modelowi",
                shown_for_claims=["T1"],
            )
        ],
        analyzed_at="2026-11-21T12:00:00Z",
        max_source_age_days=730,
        models={"werdykt": "m"},
        prompt_version="werdykt-v1-x",
    )


def test_compact_keeps_required_source_metadata_and_quote():
    data = compact(sample())
    [evidence] = data["claims"][0]["evidence"]
    assert evidence["quote"] and evidence["source_title"] == "Akcesja"
    assert evidence["publisher"] == "Wydawca" and evidence["published_at"] == "2026-11-21"
    assert "url" in evidence and evidence["url"] is None, "link zostaje jako null, gdy go brak"
    for source in data["sources"] + data["input_sources"]:
        for key in ("title", "publisher", "published_at", "url"):
            assert key in source, (source["source_id"], key)


def test_compact_applies_trimming_rules_1_to_6():
    data = compact(sample())
    claim = data["claims"][0]
    assert all("text" not in s for s in data["sources"])  # 1
    assert claim["sources_reviewed"][1] == {
        "source_id": "UZ-1",
        "relevant": False,
        "why": "Inny temat",
    }  # 2
    assert claim["source_freshness"] == [  # 3
        {"source_id": "UZ-1", "age_days": 5478, "freshness_flags": ["material_archiwalny"]}
    ]
    for key in ("context", "verdict_label", "source_ids", "model", "model_verdict"):  # 4, 5
        assert key not in claim
    assert not {"fetched_at", "age_days", "freshness_flags"} & set(claim["evidence"][0])  # 5
    assert "conflicts" not in claim and "warnings" not in data  # 6 (puste listy)
    assert claim["sources_reviewed"][1]["relevant"] is False, "False nie jest pustą wartością"


def test_model_verdict_is_kept_when_control_changed_it():
    verdict = sample()
    verdict.claims[0].verdict = "brak_wystarczajacych_danych"
    data = compact(verdict)
    assert data["claims"][0]["model_verdict"] == "prawda"


def test_compact_is_much_shorter_and_serializable():
    full = sample().model_dump_json(indent=2)
    short = json.dumps(compact(sample()), ensure_ascii=False, indent=2)
    assert len(short) < 0.75 * len(full)
