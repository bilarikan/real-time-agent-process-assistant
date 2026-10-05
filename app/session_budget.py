"""Wall-clock, token, and model-turn limits for a Live session."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    seconds: int
    tokens: int
    turns: int

    @classmethod
    def from_env(cls) -> BudgetLimits:
        return cls(
            seconds=_positive_env("SESSION_BUDGET_SECONDS", 2100),
            tokens=_positive_env("SESSION_BUDGET_TOKENS", 1_000_000),
            turns=_positive_env("SESSION_BUDGET_TURNS", 250),
        )


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    elapsed_seconds: int
    cumulative_tokens: int
    estimated_cost_usd: float
    turns: int
    usage_fraction: float
    warning: bool
    exhausted: bool

    def as_dict(self) -> dict[str, int | float | bool]:
        return {
            "elapsedSeconds": self.elapsed_seconds,
            "cumulativeTokens": self.cumulative_tokens,
            "estimatedCostUsd": round(self.estimated_cost_usd, 4),
            "turns": self.turns,
            "usageFraction": round(self.usage_fraction, 4),
            "warning": self.warning,
            "exhausted": self.exhausted,
        }


class SessionBudget:
    """Tracks unique usage events so repeated serialization cannot double count."""

    def __init__(
        self,
        limits: BudgetLimits,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits
        self._clock = clock
        self._started_at = clock()
        self._seen_usage_events: set[str] = set()
        self.cumulative_tokens = 0
        self.estimated_cost_usd = 0.0
        self.turns = 0

    def record_usage(
        self,
        event_id: str,
        total_tokens: int,
        *,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        if event_id in self._seen_usage_events:
            return
        if total_tokens < 0:
            raise ValueError("total_tokens must not be negative")
        if estimated_cost_usd < 0:
            raise ValueError("estimated_cost_usd must not be negative")
        self._seen_usage_events.add(event_id)
        self.cumulative_tokens += total_tokens
        self.estimated_cost_usd += estimated_cost_usd

    def record_turn(self) -> None:
        self.turns += 1

    def snapshot(self) -> BudgetSnapshot:
        elapsed = max(int(self._clock() - self._started_at), 0)
        fractions = (
            elapsed / self.limits.seconds,
            self.cumulative_tokens / self.limits.tokens,
            self.turns / self.limits.turns,
        )
        usage_fraction = max(fractions)
        return BudgetSnapshot(
            elapsed_seconds=elapsed,
            cumulative_tokens=self.cumulative_tokens,
            estimated_cost_usd=self.estimated_cost_usd,
            turns=self.turns,
            usage_fraction=usage_fraction,
            warning=usage_fraction >= 0.8,
            exhausted=usage_fraction >= 1.0,
        )


def _positive_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value
