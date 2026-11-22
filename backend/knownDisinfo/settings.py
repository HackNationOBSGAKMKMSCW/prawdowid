"""Environment-backed settings for the EUvsDisinfo check."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
# Wsteczna kompatybilność dla istniejącego lokalnego backend/.env.
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=False)

DEFAULT_MCP_URL = "https://mcp.euvsd.info/mcp"


def _number(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class DisinfoSettings:
    api_key: str | None = field(default=None, repr=False)
    mcp_url: str = DEFAULT_MCP_URL
    timeout: float = 20.0
    max_candidates: int = 5
    max_queries: int = 3
    max_concurrency: int = 4
    enabled: bool = True

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    @classmethod
    def from_environment(cls) -> "DisinfoSettings":
        # The team's name for the key; the upper-case spelling is accepted too.
        key = os.getenv("EUvsDisinfo_API_KEY") or os.getenv("EUVSDISINFO_API_KEY") or ""  # noqa: SIM112
        return cls(
            api_key=key.strip().strip('"').strip("'") or None,
            mcp_url=(os.getenv("EUVSDISINFO_MCP_URL") or DEFAULT_MCP_URL).strip(),
            timeout=max(1.0, _number("EUVSDISINFO_MCP_TIMEOUT", 20.0)),
            max_candidates=max(1, int(_number("KNOWN_DISINFO_MAX_CANDIDATES", 5))),
            enabled=os.getenv("KNOWN_DISINFO_ENABLED", "true").strip().lower()
            not in {"0", "false", "no"},
        )
