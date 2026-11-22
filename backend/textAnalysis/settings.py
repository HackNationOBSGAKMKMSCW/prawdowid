"""Environment-backed settings shared by standalone analysis and reader calls."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
# Wsteczna kompatybilność dla istniejącego lokalnego backend/.env.
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration; API clients never read or log secrets themselves."""

    freellm_api_key: str | None
    freellm_base_url: str | None
    freellm_model: str
    google_fact_check_api_key: str | None
    llm_timeout: float
    llm_max_retries: int
    diffbot_api_token: str | None = field(default=None, repr=False)
    article_scraping_enabled: bool = True
    article_max_concurrency: int = 1
    article_batch_timeout: float = 60.0
    article_extractor: str = "local"
    article_max_links: int = 5
    article_max_user_links: int = 2

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            freellm_api_key=os.getenv("FREELLM_API_KEY"),
            freellm_base_url=os.getenv("FREELLM_BASE_URL"),
            freellm_model=os.getenv("FREELLM_MODEL", "gpt-4o-mini"),
            google_fact_check_api_key=os.getenv("GOOGLE_FACT_CHECK_API_KEY"),
            llm_timeout=float(os.getenv("FREELLM_TIMEOUT", "30")),
            llm_max_retries=int(os.getenv("FREELLM_MAX_RETRIES", "2")),
            diffbot_api_token=os.getenv("DIFFBOT_API_TOKEN"),
            article_scraping_enabled=os.getenv("ARTICLE_SCRAPING_ENABLED", "true").lower()
            not in {"0", "false", "no"},
            article_max_concurrency=max(1, int(os.getenv("ARTICLE_MAX_CONCURRENCY", "1"))),
            article_batch_timeout=float(os.getenv("ARTICLE_BATCH_TIMEOUT", "60")),
            article_extractor=os.getenv("ARTICLE_EXTRACTOR", "local").strip().lower(),
            article_max_links=max(1, int(os.getenv("ARTICLE_MAX_LINKS", "5"))),
            article_max_user_links=max(0, int(os.getenv("ARTICLE_MAX_USER_LINKS", "2"))),
        )
