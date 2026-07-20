#!/usr/bin/env python3
"""
Lightweight token metrics and cost calculation for the agent container.

This is a slimmed-down copy of evaluation/metrics.py containing ONLY what
the agent needs at runtime (TokenMetrics + calculate_cost).  The full
evaluation-related classes (EvalResult, CheckResult, RunResult) live in
evaluation/metrics.py and are used only on the host side.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# Model pricing per 1M tokens (USD)
# ============================================================================

MODEL_PRICING = {
    # OpenAI
    "gpt-5.2": {"input": 1.75, "cached_input": 0.175, "cache_write": 1.75, "output": 14.00},
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "cache_write": 2.50, "output": 10.00},
    "o3": {"input": 10.00, "cached_input": 2.50, "cache_write": 10.00, "output": 40.00},
    # Anthropic (via OpenRouter)
    "anthropic/claude-sonnet-4.5": {"input": 3.00, "cached_input": 0.30, "cache_write": 3.75, "output": 15.00},
    "anthropic/claude-opus-4.5": {"input": 15.00, "cached_input": 1.50, "cache_write": 18.75, "output": 75.00},
    # Local, self-hosted — no per-token cost.
    "sft-agent": {"input": 0.0, "cached_input": 0.0, "cache_write": 0.0, "output": 0.0},
}


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    cache_write_tokens: int,
    model: str,
) -> Tuple[float, float]:
    """Return ``(actual_cost_usd, cost_without_cache_usd)``."""
    pricing = None
    for key in MODEL_PRICING:
        if model == key or model.endswith(key):
            pricing = MODEL_PRICING[key]
            break
    if pricing is None:
        pricing = MODEL_PRICING.get("gpt-5.2", {"input": 2.5, "cached_input": 1.25, "cache_write": 2.5, "output": 10.0})

    non_cached = max(0, input_tokens - cached_tokens - cache_write_tokens)
    actual = (
        (non_cached / 1e6) * pricing["input"]
        + (cached_tokens / 1e6) * pricing["cached_input"]
        + (cache_write_tokens / 1e6) * pricing.get("cache_write", pricing["input"])
        + (output_tokens / 1e6) * pricing["output"]
    )
    without_cache = (
        (input_tokens / 1e6) * pricing["input"]
        + (output_tokens / 1e6) * pricing["output"]
    )
    return actual, without_cache


# ============================================================================
# TokenMetrics
# ============================================================================

@dataclass
class TokenMetrics:
    """Accumulated token metrics from SDK responses."""
    message_count: int = 0
    max_context_size: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost_usd: float = 0.0
    total_cost_without_cache_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def cache_hit_rate(self) -> float:
        if self.total_input_tokens == 0:
            return 0.0
        return (self.total_cached_tokens / self.total_input_tokens) * 100

    @property
    def cache_savings_usd(self) -> float:
        return max(0.0, self.total_cost_without_cache_usd - self.total_cost_usd)

    def to_dict(self) -> dict:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_cache_write_tokens": self.total_cache_write_tokens,
            "cache_hit_rate_percent": round(self.cache_hit_rate, 2),
            "total_tokens": self.total_tokens,
            "message_count": self.message_count,
            "max_context_size": self.max_context_size,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_cost_without_cache_usd": round(self.total_cost_without_cache_usd, 4),
            "cache_savings_usd": round(self.cache_savings_usd, 4),
        }
