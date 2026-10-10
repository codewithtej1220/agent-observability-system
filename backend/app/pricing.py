"""Estimated model pricing (USD per 1M tokens: input, output).

Used only to show an *estimated* cost next to token counts. Update these
to your contracted rates; unknown models fall back to DEFAULT_PRICE.
"""
from __future__ import annotations

from typing import Dict, Tuple

MODEL_PRICES: Dict[str, Tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-opus-4-1": (15.00, 75.00),
    "gemini-2.5-flash": (0.30, 2.50),
}
DEFAULT_PRICE = (1.00, 4.00)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = MODEL_PRICES.get(model, DEFAULT_PRICE)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000
