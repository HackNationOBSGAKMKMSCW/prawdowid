"""WhatsApp demo adapter for SprawdzTo: Cloud API message shapes, bot, and server."""

from .bot import SprawdzToBot
from .pipeline import CheckReport, DemoPipeline, LivePipeline

__all__ = ["CheckReport", "DemoPipeline", "LivePipeline", "SprawdzToBot"]
