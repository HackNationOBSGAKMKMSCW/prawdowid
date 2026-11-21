from prawdowid_analysis.schemas import ReferenceSource
from prawdowid_analysis.sources import (
    DEFAULT_CORPUS_DIR,
    Retriever,
    chunk_text,
    load_documents,
    split_source,
    tokenize,
)


def test_tokenize_folds_diacritics_and_inflection():
    assert tokenize("Stolicą Polski") == tokenize("stolica polski")
    assert "2004" in tokenize("w 2004 roku")
    assert "w" not in tokenize("w Polsce")


def test_chunk_text_respects_limit_and_keeps_content():
    text = "\n\n".join(f"Akapit numer {i}. " + "słowo " * 30 for i in range(10))
    chunks = chunk_text(text, max_chars=300)
    assert all(len(c) <= 300 for c in chunks)
    assert "Akapit numer 9." in chunks[-1]


def test_split_source_assigns_fragment_ids():
    source = ReferenceSource(source_id="DOC", kind="uzytkownik", text="\n\n".join(["x " * 200] * 3))
    parts = split_source(source, max_chars=450)
    assert len(parts) > 1
    assert parts[0].source_id == "DOC#1"
    assert all(p.kind == "uzytkownik" for p in parts)


def test_default_corpus_loads():
    documents = load_documents(DEFAULT_CORPUS_DIR)
    assert {d.source_id for d in documents} >= {"KOR-polska-ue", "KOR-szczyty"}
    assert all(d.kind == "korpus" for d in documents)


def test_retriever_finds_relevant_passage_first():
    retriever = Retriever.from_directory()
    hits = retriever.search("Kiedy Polska przystąpiła do Unii Europejskiej?", k=3)
    assert hits
    assert hits[0][0].source_id.startswith("KOR-polska-ue")


def test_retriever_returns_nothing_for_unrelated_query():
    retriever = Retriever.from_directory()
    assert retriever.search("kwantowa chromodynamika gluonów") == []


def test_retriever_handles_empty_pool():
    assert Retriever([]).search("cokolwiek") == []


def test_expand_query_adds_only_matching_keywords():
    from prawdowid_analysis.sources import expand_query

    keywords = ["Rysy", "szczepionka", "Unia Europejska"]
    assert (
        expand_query("Wysokość Rysów wynosi 2499 m.", keywords)
        == "Wysokość Rysów wynosi 2499 m. Rysy"
    )
    assert expand_query("Ala ma kota.", keywords) == "Ala ma kota."


def test_keyword_expansion_finds_passage_missed_by_stemming():
    from prawdowid_analysis.schemas import ReferenceSource
    from prawdowid_analysis.sources import expand_query

    doc = ReferenceSource(source_id="D", kind="korpus", text="Rysy są najwyższym szczytem.")
    retriever = Retriever([doc])
    claim = "Rysów nikt nie zdobył."
    assert retriever.search(claim, min_score=1e-9) == []
    assert retriever.search(expand_query(claim, ["Rysy"]), min_score=1e-9)


def test_context_excerpt_short_text_long_text_and_no_value():
    from prawdowid_analysis.sources import context_excerpt

    assert context_excerpt("Ala ma kota.", "Ala ma kota.") is None
    short = "Prezydent Nowak przemawiał w Sejmie. On podpisał ustawę."
    assert context_excerpt("On podpisał ustawę.", short) == short
    filler = " ".join(f"Zdanie wypełniające numer {i}." for i in range(80))
    long_text = f"{filler} Prezydent Nowak przemawiał. On podpisał ustawę o lasach. {filler}"
    excerpt = context_excerpt("Podpisał ustawę o lasach.", long_text, max_chars=300)
    assert "Prezydent Nowak przemawiał." in excerpt and "ustawę o lasach" in excerpt
    assert len(excerpt) <= 300
    assert context_excerpt("Kwantowa chromodynamika.", long_text, max_chars=300) is None
