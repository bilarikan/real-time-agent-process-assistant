from __future__ import annotations

import pytest

from app.sales_agent.calculator import calculate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("(1299 - 899) / 365 * 197", "Result: 215.8904109589"),
        ("1299 * 15 / 100", "Result: 194.85"),
        ("0.1 + 0.2", "Result: 0.3"),
        ("round(2.345, 2)", "Result: 2.35"),
        ("max(1, 2, 3) - min(4, 5)", "Result: -1"),
        ("$1299 × 12 ÷ 100", "Result: 155.88"),
        ('days_between("2026-06-12", "2027-03-26")', "Result: 287"),
        ('add_days("09/15/2026", 30)', "Result: 2026-10-15 (Thu 15 Oct 2026)"),
        ("= 8277 / 12 =", "Result: 689.75"),
    ],
)
def test_calculate_returns_exact_results(expression: str, expected: str) -> None:
    result = calculate(expression)

    assert result.startswith("CALCULATION\n")
    assert expected in result.splitlines()


def test_calculate_adds_a_cent_rounded_value_for_fractions() -> None:
    result = calculate("(1299 - 899) / 365 * 197")

    assert "Rounded to cents: 215.89" in result.splitlines()


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("1,299 * 2", "thousands separators"),
        ("10 % 3", "write percentages explicitly"),
        ("1 / 0", "division by zero"),
        ("2 ** 10", "only +, -, *, and / are supported"),
        ("__import__('os')", "unknown function '__import__'"),
        ("open('x')", "unknown function 'open'"),
        ("x + 1", "unknown name 'x'"),
        ("1e13 * 10", "values above"),
        ('days_between("2026-06-12", 5)', "dates must be quoted"),
        ('add_days("2026-02-30", 1)', "not a real calendar date"),
        ("", "the expression is empty"),
        ("(1 + ", "not valid arithmetic"),
    ],
)
def test_calculate_refuses_unsupported_input(expression: str, reason: str) -> None:
    result = calculate(expression)

    assert result.startswith("CALCULATION NOT PERFORMED")
    assert reason in result
