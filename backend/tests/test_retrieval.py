import hashlib

from retrieval import _MOCK_DOCS, get_retriever, mock_retrieve
from schemas import Passage


def test_mock_returns_3_to_4_passages_in_contract_format():
    passages = mock_retrieve("Czy opłata za paszport wzrośnie?")
    assert 3 <= len(passages) <= 4
    assert all(isinstance(p, Passage) for p in passages)


def test_offsets_and_hash_match_clean_text():
    docs = {d.doc_id: d for d in _MOCK_DOCS}
    for p in mock_retrieve("paszport", k=10):
        clean_text = docs[p.doc_id].clean_text
        assert clean_text[p.char_start : p.char_end] == p.text
        expected = "sha256:" + hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
        assert p.text_hash == expected


def test_ranking_is_by_query_overlap():
    passages = mock_retrieve("opłata paszportowa wzrośnie trzykrotnie")
    assert passages[0].doc_id == "mock_doc_003"
    scores = [p.rerank_score for p in passages]
    assert scores == sorted(scores, reverse=True)


def test_k_and_source_type_filter():
    assert len(mock_retrieve("paszport", k=2)) == 2
    only_official = mock_retrieve("paszport", filters={"source_type": ["official_primary"]})
    assert only_official
    assert {p.source_type for p in only_official} == {"official_primary"}


def test_get_retriever_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("RETRIEVER", raising=False)
    assert get_retriever() is mock_retrieve
