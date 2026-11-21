"""Registered third-party API clients."""

from .dane_gov import DaneGovClient
from .eurlex import EurLexClient
from .google_fact_check import GoogleFactCheckClient
from .sejm import SejmApiClient
from .sejm_eli import SejmEliClient

CLIENT_CLASSES = (
    GoogleFactCheckClient,
    SejmEliClient,
    SejmApiClient,
    EurLexClient,
    DaneGovClient,
)

__all__ = [
    "CLIENT_CLASSES",
    "DaneGovClient",
    "EurLexClient",
    "GoogleFactCheckClient",
    "SejmApiClient",
    "SejmEliClient",
]
