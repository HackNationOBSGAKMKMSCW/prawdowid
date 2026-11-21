"""Public entry point for fetching data related to an analysis object."""

from .full_text import run_full_text
from .reading import run

__all__ = ["run", "run_full_text"]
