"""Environment-backed settings shared by standalone analysis and reader calls."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime configuration; API clients never read or log secrets themselves."""

    freelmm_api_key: str | None
    freelmm_base_url: str | None
    freelmm_model: str
    google_fact_check_api_key: str | None
    llm_timeout: float
    llm_max_retries: int

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            freelmm_api_key=os.getenv("FREELLM_API_KEY"),
            freelmm_base_url=os.getenv("FREELLM_BASE_URL"),
            freelmm_model=os.getenv("FREELLM_MODEL", "gpt-4o-mini"),
            google_fact_check_api_key=os.getenv("GOOGLE_FACT_CHECK_API_KEY"),
            llm_timeout=float(os.getenv("FREELLM_TIMEOUT", "30")),
            llm_max_retries=int(os.getenv("FREELLM_MAX_RETRIES", "2")),
        )
