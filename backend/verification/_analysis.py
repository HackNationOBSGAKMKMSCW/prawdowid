"""Lazy import of the assessment packages that live in ``analysis/``.

* ``inputDataAnalysis`` (``analysis/inputDataAnalysis``): manipulation + date checks of the input,
* ``prawdowid_analysis`` (``analysis/src/prawdowid_analysis``): verdict for each claim.

The directories are appended (not prepended) to ``sys.path`` so ``analysis/scripts`` and
``analysis/tests`` never shadow the backend packages of the same name. Override the location
with ``PRAWDOWID_ANALYSIS_DIR``.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

DEFAULT_ANALYSIS_DIR = Path(__file__).resolve().parents[2] / "analysis"


class AnalysisUnavailable(RuntimeError):
    """The ``analysis/`` packages cannot be imported."""


def analysis_dir() -> Path:
    override = os.getenv("PRAWDOWID_ANALYSIS_DIR", "").strip()
    return Path(override) if override else DEFAULT_ANALYSIS_DIR


def add_paths() -> None:
    base = analysis_dir()
    for path in (base, base / "src"):
        if str(path) not in sys.path:
            sys.path.append(str(path))


def _import(name: str) -> ModuleType:
    add_paths()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            return importlib.import_module(name)
    except ImportError as exc:
        raise AnalysisUnavailable(
            f"Nie można zaimportować {name} z {analysis_dir()}: {exc}"
        ) from exc


@cache
def input_analysis() -> ModuleType:
    """``inputDataAnalysis`` with its LLM settings loaded first.

    Both analysis stages use the shared model configuration from the project-root ``.env``.
    Input-analysis-specific generation parameters remain independently configurable.
    """
    module = _import("inputDataAnalysis")
    with contextlib.suppress(RuntimeError):  # missing config surfaces on the first call instead
        importlib.import_module("inputDataAnalysis.config").get_settings()
    return module


@cache
def verdict_pipeline() -> ModuleType:
    """``prawdowid_analysis.pipeline`` (claim verdicts)."""
    input_analysis()  # see the ordering note above
    return _import("prawdowid_analysis.pipeline")


@cache
def verdict_schemas() -> ModuleType:
    verdict_pipeline()
    return _import("prawdowid_analysis.schemas")


@cache
def verdict_aggregate() -> ModuleType:
    """``prawdowid_analysis.aggregate`` (text verdict from claim verdicts, no LLM)."""
    verdict_pipeline()
    return _import("prawdowid_analysis.aggregate")
