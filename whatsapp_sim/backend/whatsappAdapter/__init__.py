"""WhatsApp demo adapter for SprawdzTo: Cloud API message shapes, bot, and server."""

import sys
from pathlib import Path

# The fact-check packages (textAnalysis, apiReading) live in the main app's
# backend/ directory; make them importable when running from whatsapp_sim/.
_MAIN_BACKEND = Path(__file__).resolve().parents[3] / "backend"
if _MAIN_BACKEND.is_dir() and str(_MAIN_BACKEND) not in sys.path:
    sys.path.append(str(_MAIN_BACKEND))

from .bot import SprawdzToBot  # noqa: E402
from .pipeline import CheckReport, DemoPipeline, LivePipeline  # noqa: E402

__all__ = ["CheckReport", "DemoPipeline", "LivePipeline", "SprawdzToBot"]
