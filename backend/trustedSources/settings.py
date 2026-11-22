"""Environment-backed settings for the trusted-source search."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class TrustedSettings:
    source_timeout: float = 6.0
    cache_ttl: float = 1200.0
    query_cache_ttl: float = 600.0
    max_concurrency: int = 8
    max_hits: int = 10
    max_hits_per_source: int = 3
    google_fact_check_api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls) -> "TrustedSettings":
        return cls(
            source_timeout=max(0.5, _float("TRUSTED_SOURCE_TIMEOUT", 6.0)),
            cache_ttl=max(0.0, _float("TRUSTED_SOURCE_CACHE_TTL", 1200.0)),
            google_fact_check_api_key=os.getenv("GOOGLE_FACT_CHECK_API_KEY") or None,
        )
