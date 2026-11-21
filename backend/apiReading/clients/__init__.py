"""Registered third-party API clients."""

from .google_fact_check import GoogleFactCheckClient

CLIENT_CLASSES = (GoogleFactCheckClient,)

__all__ = ["CLIENT_CLASSES", "GoogleFactCheckClient"]
