import pytest

from prawdowid_analysis.quotes import verify_quote

SOURCE = (
    "W referendum za przystąpieniem opowiedziało się 77,45% głosujących.\n"
    "Polska nie przyjęła wspólnej waluty euro. Traktat — podpisany w „Atenach”."
)


def test_exact_quote_returns_source_span():
    assert verify_quote("Polska nie przyjęła wspólnej waluty euro", SOURCE) == (
        "Polska nie przyjęła wspólnej waluty euro"
    )


def test_typography_whitespace_and_case_are_normalized():
    span = verify_quote("opowiedziało się 77,45% Głosujących", SOURCE)
    assert span == "opowiedziało się 77,45% głosujących"
    assert (
        verify_quote('Traktat - podpisany w "Atenach"', SOURCE) == "Traktat — podpisany w „Atenach"
    )


def test_surrounding_quotes_and_period_are_ignored():
    assert verify_quote("„Polska nie przyjęła wspólnej waluty euro.”", SOURCE) is not None


@pytest.mark.parametrize(
    "quote",
    [
        "opowiedziało się 77,46% głosujących",  # zmieniona liczba
        "Polska przyjęła wspólną walutę euro",  # usunięta negacja / parafraza
        "Polska nie przyjęła ... euro",  # wielokropek
        "euro",  # za krótki
        "",
    ],
)
def test_altered_or_trivial_quotes_are_rejected(quote):
    assert verify_quote(quote, SOURCE) is None
