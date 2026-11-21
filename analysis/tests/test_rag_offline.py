"""Testy RAG bez sieci: chunking, sparse, dedupe na fałszywym store."""

import json
from pathlib import Path

import pytest

from prawdowid_analysis.rag.chunking import chunk_text, split_sentences
from prawdowid_analysis.rag.ingest import (
    build_payloads,
    ingest_sources,
    make_doc_id,
    normalize_url,
)
from prawdowid_analysis.rag.mock import mock_retrieve
from prawdowid_analysis.rag.retriever import get_retriever
from prawdowid_analysis.rag.sparse import sparse_vector, tokenize
from prawdowid_analysis.schemas import AnalysisInput, Passage, SourceIn

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "samples" / "sample_input.json"

TEXT = (
    "Zgodnie z art. 5 ust. 2 ustawy wniosek składa się osobiście. "
    "Opłata wynosi 140 zł. Od 1 stycznia 2027 r. zmienia się tryb odbioru!\n\n"
    "Nowe zasady. Dokument można odebrać w dowolnym urzędzie? Tak, m.in. w urzędzie "
    "wojewódzkim."
)


# ── chunking ──


def test_sentences_respect_abbreviations():
    sents = [TEXT[s:e] for s, e in split_sentences(TEXT)]
    assert sents[0] == "Zgodnie z art. 5 ust. 2 ustawy wniosek składa się osobiście."
    assert "Nowe zasady." in sents
    assert sents[-1].startswith("Tak, m.in. w urzędzie")


@pytest.mark.parametrize("max_chars", [40, 120, 800])
def test_chunk_offsets_match_clean_text(max_chars):
    chunks = chunk_text(TEXT, max_chars=max_chars)
    assert chunks
    for ch in chunks:
        assert TEXT[ch.start : ch.end] == ch.text
        assert ch.text == ch.text.strip()
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunks_overlap_one_sentence_and_cover_text():
    chunks = chunk_text(TEXT, max_chars=120)
    sents = split_sentences(TEXT)
    assert len(chunks) > 1
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.start > a.start  # postęp
        n_sent_a = sum(1 for s, e in sents if s >= a.start and e <= a.end)
        if n_sent_a > 1:
            # następny chunk zaczyna się od ostatniego zdania poprzedniego
            assert (b.start, a.end) in [(s, e) for s, e in sents]
        else:
            assert b.start > a.end  # pojedyncze zdanie: bez nakładania
    assert chunks[0].start == 0
    assert chunks[-1].end == len(TEXT.rstrip())


def test_chunk_size_limit_except_single_long_sentence():
    chunks = chunk_text(TEXT, max_chars=120)
    sents = split_sentences(TEXT)
    for ch in chunks:
        n_sent = sum(1 for s, e in sents if s >= ch.start and e <= ch.end)
        assert len(ch.text) <= 120 or n_sent == 1


# ── sparse ──


def test_tokenize_drops_stopwords_and_stems():
    toks = tokenize("Wniosek o wydanie paszportu i paszporty")
    assert "o" not in toks and "i" not in toks
    assert toks.count("paszpo") == 2


def test_sparse_vector_is_deterministic_and_sorted():
    a = sparse_vector("opłata paszportowa wzrośnie opłata")
    b = sparse_vector("opłata paszportowa wzrośnie opłata")
    assert a == b
    assert a["indices"] == sorted(a["indices"])
    assert len(a["indices"]) == len(a["values"]) == 3
    assert max(a["values"]) > min(a["values"])  # "opłata" x2
    q = sparse_vector("opłata", is_query=True)
    assert q["values"] == [1.0]
    assert sparse_vector("i o w") == {"indices": [], "values": []}


# ── ingest / dedupe ──


class FakeEmbedder:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += len(texts)
        return [[float(len(t)), 1.0, 0.0] for t in texts]


class FakeStore:
    def __init__(self):
        self.points: dict[str, dict] = {}
        self.dim = None

    def ensure_collection(self, dim):
        self.dim = dim

    def get_doc_hash(self, doc_id):
        for p in self.points.values():
            if p["payload"]["doc_id"] == doc_id:
                return p["payload"]["text_hash"]
        return None

    def delete_doc(self, doc_id):
        self.points = {k: v for k, v in self.points.items() if v["payload"]["doc_id"] != doc_id}

    def upsert(self, points):
        for p in points:
            self.points[p["id"]] = p


def _src(url="https://example.org/a", text=TEXT):
    return SourceIn(
        url=url,
        title="T",
        publisher="P",
        published_at="2026-10-03",
        fetched_at="2026-11-21T10:15:32Z",
        source_type="official_primary",
        text=text,
    )


def test_normalize_url_and_doc_id():
    a = "HTTPS://Example.org/a/?utm_source=x&b=2#frag"
    assert normalize_url(a) == "https://example.org/a?b=2"
    assert make_doc_id(a) == make_doc_id("https://example.org/a?b=2")
    assert make_doc_id(a).startswith("doc_") and len(make_doc_id(a)) == 16


def test_payloads_validate_as_passages():
    src = _src()
    for p in build_payloads(src, max_chars=120):
        passage = Passage.model_validate({**p, "rerank_score": 0.0})
        assert src.text[passage.char_start : passage.char_end] == passage.text


def test_ingest_added_skipped_replaced():
    store, emb = FakeStore(), FakeEmbedder()
    r1 = ingest_sources([_src(), _src("https://example.org/a/")], store, emb, max_chars=120)
    assert (r1.added, r1.skipped, r1.replaced) == (1, 1, 0)
    n_points, n_calls = len(store.points), emb.calls

    r2 = ingest_sources([_src()], store, emb, max_chars=120)
    assert (r2.added, r2.skipped, r2.replaced) == (0, 1, 0)
    assert emb.calls == n_calls  # pominięty dokument nie jest embedowany
    assert len(store.points) == n_points

    r3 = ingest_sources([_src(text="Zupełnie nowy tekst.")], store, emb, max_chars=120)
    assert (r3.added, r3.skipped, r3.replaced) == (0, 0, 1)
    assert len(store.points) == 1  # stare chunki usunięte


# ── atrapa i dane przykładowe ──


def test_mock_retriever_contract():
    assert get_retriever("mock") is mock_retrieve
    res = mock_retrieve("opłata paszportowa wzrośnie", k=6)
    assert 0 < len(res) <= 4
    assert all(isinstance(p, Passage) for p in res)
    with pytest.raises(ValueError):
        get_retriever("nope")


def test_sample_input_is_valid():
    data = AnalysisInput.model_validate(json.loads(SAMPLE.read_text(encoding="utf-8")))
    assert len(data.claims) >= 6 and len(data.sources) >= 8
    doc_ids = [make_doc_id(s.url) for s in data.sources]
    assert len(doc_ids) - len(set(doc_ids)) == 1  # dokładnie jeden duplikat URL
