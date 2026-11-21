import pytest

from prawdowid_analysis.rag.mock import mock_retrieve
from prawdowid_analysis.verdict.quotes import verify_quote

TEXT = (
    "Od 1 stycznia 2027 r. wniosek o wydanie paszportu można złożyć w dowolnym "
    "urzędzie wojewódzkim, niezależnie od miejsca zameldowania. "
    "Opłata za wydanie paszportu dla osoby dorosłej nie ulega zmianie."
)


def test_exact_quote_is_verified_with_offsets():
    quote = "wniosek o wydanie paszportu można złożyć w dowolnym urzędzie wojewódzkim"
    m = verify_quote(quote, TEXT)
    assert m.verified and m.score == 100.0
    assert TEXT[m.char_start : m.char_end] == m.matched_text == quote


@pytest.mark.parametrize(
    "quote",
    [
        "Wniosek o wydanie paszportu  można\nzłożyć w dowolnym urzędzie",  # wielkość liter, spacje
        "„wniosek o wydanie paszportu można złożyć w dowolnym urzędzie”",  # cudzysłowy
        "niezależnie od miejsca zameldowania...",  # wielokropek na końcu
    ],
)
def test_normalized_quote_is_verified_and_points_to_source_text(quote):
    m = verify_quote(quote, TEXT)
    assert m.verified
    assert m.matched_text == TEXT[m.char_start : m.char_end]
    assert m.matched_text in TEXT


def test_small_typo_passes_fuzzy_threshold():
    m = verify_quote("wniosek o wydanie paszportu mozna złożyć w dowolnym urzędzie", TEXT)
    assert m.verified and m.score < 100
    assert "paszportu można złożyć" in m.matched_text


@pytest.mark.parametrize(
    "quote",
    [
        "wniosek o wydanie paszportu można złożyć wyłącznie w urzędzie gminy",  # zmyślony
        "Od 1 stycznia 2028 r. wniosek o wydanie paszportu",  # zmieniona liczba
        "Opłata za wydanie paszportu dla osoby dorosłej ulega zmianie",  # zgubione "nie"
        "paszport",  # za krótki
        "",
        TEXT + " Opłata wzrośnie trzykrotnie.",  # dłuższy niż pasaż
    ],
)
def test_fabricated_or_unusable_quote_is_rejected(quote):
    m = verify_quote(quote, TEXT)
    assert not m.verified
    assert m.char_start is None and m.matched_text == ""


def test_offsets_map_back_to_document_on_mock_passage():
    passage = mock_retrieve("opłata za wydanie paszportu", k=1)[0]
    m = verify_quote("Opłata za wydanie paszportu dla osoby dorosłej", passage.text)
    assert m.verified
    doc_start = passage.char_start + m.char_start
    doc_end = passage.char_start + m.char_end
    assert doc_end - doc_start == len(m.matched_text)
