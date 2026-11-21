import pytest
from articleScraping.url_validation import InvalidUrlError, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:pass@example.com/article",
        "http://localhost/article",
        "http://news.local/article",
        "http://news.internal/article",
        "http://news.lan/article",
        "http://127.0.0.1/article",
        "http://2130706433/article",
        "http://0x7f000001/article",
        "http://0177.0.0.1/article",
        "http://[::1]/article",
        "http://[::ffff:127.0.0.1]/article",
        "https://example.com:444/article",
        "https://example.com\\@evil.test/article",
        "https://example.com/has space",
        "https://example.com/" + "x" * 2048,
        "http://singlelabel/article",
        "http://[malformed/article",
    ],
)
def test_validate_url_rejects_malformed_or_non_public_urls(url: str) -> None:
    with pytest.raises(InvalidUrlError):
        validate_url(url)


def test_validate_url_canonicalizes_idn_ports_fragments_and_trailing_dot() -> None:
    assert (
        validate_url("HTTPS://BÜCHER.example.:443/path#section")
        == "https://xn--bcher-kva.example/path"
    )
    assert validate_url("http://example.com:443/a") == "http://example.com:443/a"


def test_validate_url_preserves_query_without_interpreting_diffbot_parameters() -> None:
    url = "https://example.com/a?x=1&token=untrusted#fragment"

    assert validate_url(url) == "https://example.com/a?x=1&token=untrusted"
