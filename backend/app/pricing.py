"""Estimated model pricing (USD per 1M tokens: input, output).

Used only to show an *estimated* cost next to token counts. Update these
to your contracted rates; unknown models fall back to DEFAULT_PRICE.
"""
from __future__ import annotations

from typing import Dict, Tuple

MODEL_PRICES: Dict[str, Tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "o4-mini": (1.10, 4.40),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-opus-4-1": (15.00, 75.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
}
DEFAULT_PRICE = (1.00, 4.00)


def price_of(model: str) -> Tuple[float, float]:
    """Exact match, else the longest known prefix (handles dated ids like claude-sonnet-4-5-20250929)."""
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]
    m = (model or "").split("/")[-1]
    matches = [k for k in MODEL_PRICES if m.startswith(k)]
    return MODEL_PRICES[max(matches, key=len)] if matches else DEFAULT_PRICE


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price_of(model)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
