from datetime import UTC, datetime

from articleScraping.mapping import MAX_ARTICLE_CHARS, map_article
from articleScraping.protocols import RawArticle


def test_map_article_normalizes_metadata_and_truncates_untrusted_text() -> None:
    article = map_article(
        "https://requested.example/article",
        RawArticle(
            text="Ａrticle\u200b body\x00 " + "x" * MAX_ARTICLE_CHARS,
            title="Ｔｉｔｌｅ",
            author="A\u202euthor",
            date="Wed, 18 Nov 2026 08:00:00 GMT",
            resolved_page_url="http://127.0.0.1/internal",
        ),
    )

    assert article.url == "https://requested.example/article"
    assert article.title == "Title"
    assert article.author == "Author"
    assert article.published_at == datetime(2026, 11, 18, 8, tzinfo=UTC)
    assert article.text.startswith("Article body")
    assert len(article.text) == MAX_ARTICLE_CHARS
    assert article.truncated is True
    assert "resolved_page_url" not in article.model_dump()


def test_missing_or_invalid_diffbot_date_is_not_guessed() -> None:
    assert map_article("https://news.example/1", RawArticle(text="body")).published_at is None
    assert (
        map_article(
            "https://news.example/1", RawArticle(text="body", date="not a date")
        ).published_at
        is None
    )


def test_cleaning_preserves_paragraph_boundaries() -> None:
    article = map_article(
        "https://news.example/paragraphs",
        RawArticle(text="First paragraph.\nSecond paragraph."),
    )

    assert article.text == "First paragraph.\nSecond paragraph."
