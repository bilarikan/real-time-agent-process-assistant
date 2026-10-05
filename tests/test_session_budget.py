from __future__ import annotations

from app.session_budget import BudgetLimits, SessionBudget


def test_budget_deduplicates_usage_events_and_warns_at_eighty_percent() -> None:
    now = [100.0]
    budget = SessionBudget(
        BudgetLimits(seconds=100, tokens=1000, turns=10),
        clock=lambda: now[0],
    )

    budget.record_usage("event-1", 800, estimated_cost_usd=0.25)
    budget.record_usage("event-1", 800, estimated_cost_usd=0.25)
    snapshot = budget.snapshot()

    assert snapshot.cumulative_tokens == 800
    assert snapshot.estimated_cost_usd == 0.25
    assert snapshot.warning is True
    assert snapshot.exhausted is False


def test_budget_exhausts_on_the_highest_limit() -> None:
    now = [10.0]
    budget = SessionBudget(
        BudgetLimits(seconds=5, tokens=1000, turns=10),
        clock=lambda: now[0],
    )
    now[0] = 15.2

    snapshot = budget.snapshot()

    assert snapshot.elapsed_seconds == 5
    assert snapshot.usage_fraction >= 1
    assert snapshot.exhausted is True
