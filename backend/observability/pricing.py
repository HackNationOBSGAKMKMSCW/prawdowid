"""Estimated LLM cost from token usage (prices in pricing.json, overridable via env)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_PRICING_FILE = Path(__file__).resolve().parent / "pricing.json"


def _read_models(path: Path) -> dict[str, tuple[float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models", data)
    return {
        key.lower(): (float(value["input"]), float(value["output"]))
        for key, value in models.items()
        if isinstance(value, dict) and "input" in value and "output" in value
    }


@lru_cache(maxsize=1)
def price_table() -> dict[str, tuple[float, float]]:
    table = _read_models(DEFAULT_PRICING_FILE)
    override = os.getenv("LOG_PRICING_FILE")
    if override and Path(override).is_file():
        table.update(_read_models(Path(override)))
    return table


def price_for(model: str | None) -> tuple[float, float] | None:
    """Return (input, output) USD per 1M tokens; longest matching key wins."""
    if not model:
        return None
    name = model.lower()
    matches = [key for key in price_table() if key in name]
    if not matches:
        return None
    return price_table()[max(matches, key=len)]


def estimate_cost(model: str | None, prompt_tokens: int, completion_tokens: int) -> float | None:
    prices = price_for(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return round((prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000, 8)
