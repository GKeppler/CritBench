#!/usr/bin/env python3
"""
Token-usage metrics and run-result recording for CritBench.

Adapted from the firmware-analyzer's ``RunResult`` and ``TokenMetrics``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


# ============================================================================
# Evaluation result
# ============================================================================

@dataclass
class CheckResult:
    """Outcome of a single evaluation check."""
    check_type: str
    passed: bool
    expected: str = ""
    actual: str = ""
    details: str = ""
    weight: float = 1.0


@dataclass
class EvalResult:
    """Aggregate evaluation outcome for a task run."""
    success: bool
    score: float  # 0.0 – 1.0
    details: List[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "score": round(self.score, 4),
            "checks": [
                {
                    "type": c.check_type,
                    "passed": c.passed,
                    "expected": c.expected,
                    "actual": c.actual[:500],
                    "details": c.details[:500],
                    "weight": c.weight,
                }
                for c in self.details
            ],
        }


# ============================================================================
# RunResult — persisted to <output>/result.json
# ============================================================================

@dataclass
class RunResult:
    """Complete result of a single CritBench task run."""

    # Core outcome
    success: bool
    exit_reason: str  # completed | token_budget_exceeded | timeout | error
    eval_result: Optional[EvalResult] = None

    # Metrics
    metrics: TokenMetrics = field(default_factory=TokenMetrics)
    total_loops: int = 0
    tool_errors: int = 0

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Identification
    task_id: str = ""
    task_type: str = ""
    model: str = ""
    token_budget: int = 0

    # Prompts (for reproducibility)
    system_prompt: str = ""
    initial_prompt: str = ""

    # Transcript path (stored separately due to size)
    transcript_path: str = ""

    def to_dict(self) -> dict:
        duration = 0.0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        return {
            "success": self.success,
            "exit_reason": self.exit_reason,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "model": self.model,
            "token_budget": self.token_budget,
            "total_loops": self.total_loops,
            "tool_errors": self.tool_errors,
            "duration_seconds": round(duration, 2),
            "start_time": self.start_time.isoformat() if self.start_time else "",
            "end_time": self.end_time.isoformat() if self.end_time else "",
            "evaluation": self.eval_result.to_dict() if self.eval_result else None,
            "metrics": self.metrics.to_dict(),
            "prompts": {
                "system_prompt": self.system_prompt,
                "initial_prompt": self.initial_prompt,
            },
            "transcript_path": self.transcript_path,
        }

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info("Wrote result to %s", path)
