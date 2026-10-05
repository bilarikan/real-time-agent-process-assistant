from __future__ import annotations

from datetime import date

import pytest

from app.sales_agent.calc_tools import (
    build_discount_note,
    compute_installment_refund,
    compute_proration,
    parse_sales_date,
)

# Example dates: 287 days remain between 2026-06-12 and 2027-03-26.
_DATES = ("2026-06-12", "2027-03-26")


@pytest.fixture
def default_day_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRORATION_DAY_BASIS", raising=False)


def _discount_note(**overrides: object) -> str:
    values: dict[str, object] = {
        "account_id": "ACCT-0001",
        "discount_type": "Campaign promotion",
        "original_amount": 1000.00,
        "adjustment_amount": 150.00,
        "total_after_adjustment": 850.00,
        "adjustment_direction": "decrease",
        "date_of_call": "2026-09-08",
        "time_of_call": "17:00 ET",
        "phone_number": "555-0100",
        "reason_for_discount": "Documented website price match",
        "sales_matrix_explored": True,
        "discount_code": "CAMPAIGN-DISCOUNT",
        "requesting_rep_id": "REP123",
        "campaign_code": "CAMP-DEMO-2026",
    }
    values.update(overrides)
    return build_discount_note(**values)  # type: ignore[arg-type]


def test_compute_installment_refund_uses_documented_formula() -> None:
    result = compute_installment_refund(1200, 3)

    assert "Formula: $1,200.00 ÷ 12 × 3" in result
    assert "Refund amount before tax: $300.00" in result
    assert "Clearing is separate" in result
    assert "one more monthly installment" in result


def test_compute_installment_refund_accepts_whole_number_floats() -> None:
    assert "Refund amount before tax: $300.00" in compute_installment_refund(1200, 3.0)


@pytest.mark.parametrize("months", [0, 13, 2.5])
def test_compute_installment_refund_rejects_invalid_months(months: float) -> None:
    with pytest.raises(ValueError, match="months_to_refund"):
        compute_installment_refund(1200, months)  # type: ignore[arg-type]


def test_build_discount_note_emits_reconciled_campaign_note() -> None:
    result = _discount_note()

    assert result.startswith("DISCOUNT APPROVAL / ORDER NOTES")
    assert "Percent adjusted: 15.00%" in result
    assert "Discount code: CAMPAIGN-DISCOUNT" in result
    assert "Campaign code: CAMP-DEMO-2026" in result


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"discount_code": "CAMPAIGN-DISCOUNT", "campaign_code": ""},
            "CAMPAIGN-DISCOUNT must be paired with a campaign code",
        ),
        (
            {"discount_code": "PRICE-FIX-UP", "campaign_code": ""},
            "PRICE-FIX-UP is only permitted to increase",
        ),
        (
            {"discount_code": "PRORATE-DOWN", "campaign_code": ""},
            "PRORATE-DOWN requires the approved proration calculation",
        ),
        (
            {"discount_code": "MGR-DISCOUNT", "campaign_code": ""},
            "MGR-DISCOUNT requires attached written manager approval",
        ),
        (
            {
                "discount_code": "PRICE-FIX-UP",
                "adjustment_direction": "increase",
                "total_after_adjustment": 1150,
                "campaign_code": "",
                "system_has_issue": True,
            },
            "PRICE-FIX-UP cannot be used while the system has an issue",
        ),
    ],
)
def test_build_discount_note_refuses_rule_violations(
    overrides: dict[str, object], expected: str
) -> None:
    result = _discount_note(**overrides)

    assert result.startswith("REFUSED")
    assert expected in result


def test_build_discount_note_accepts_price_fix_only_for_increase() -> None:
    result = _discount_note(
        discount_type="Incorrect system price",
        original_amount=850,
        adjustment_amount=150,
        total_after_adjustment=1000,
        adjustment_direction="increase",
        discount_code="price fix up",
        campaign_code="",
    )

    assert result.startswith("DISCOUNT APPROVAL / ORDER NOTES")
    assert "Discount code: PRICE-FIX-UP" in result


def test_proration_uses_365_day_basis_by_default(default_day_basis: None) -> None:
    result = compute_proration("migration", 1000, 1500, *_DATES)

    assert "Days remaining: 287 (expiry date - effective date)" in result
    assert "($1,500.00 - $1,000.00) ÷ 365 × 287 = $393.15 before tax" in result
    assert "Result: charge $393.15 before tax." in result
    assert "Basis: daily over a 365-day term" in result
    assert "Concept ID: /pricing-and-discounts/proration" in result


def test_proration_can_use_a_364_day_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRORATION_DAY_BASIS", "364")

    result = compute_proration("migration", 1000, 1500, *_DATES)

    assert "($1,500.00 - $1,000.00) ÷ 364 × 287 = $394.23 before tax" in result
    assert "Basis: daily over a 364-day term" in result


def test_migration_credit_is_reported_as_a_credit(default_day_basis: None) -> None:
    result = compute_proration("migration credit", 1000, 0, "6/12/2026", "3/26/2027")

    assert "= -$786.30 before tax" in result
    assert "prorated refund or credit of $786.30" in result
    assert "migration credit memo" in result


def test_upgrade_proration_gives_decrease_and_notes_line(default_day_basis: None) -> None:
    result = compute_proration(
        "upgrade",
        900,
        1300,
        "2026-09-15",
        "2027-03-31",
        system_order_price=1300,
    )

    assert "Days remaining: 197" in result
    assert "apply PRORATE-DOWN to decrease it by $1,084.11 to $215.89" in result
    assert (
        "Notes line: Proration: ($1,300.00 - $900.00) ÷ 365 × 197 days "
        "(2026-09-15 to 2027-03-31) = $215.89 before tax"
    ) in result


def test_proration_applies_a_dollar_discount_before_prorating(default_day_basis: None) -> None:
    result = compute_proration("upgrade", 900, 1300, "2026-09-15", "2027-03-31", discount_amount=50)

    assert "($1,300.00 - $900.00 - $50.00 discount) ÷ 365 × 197 = $188.90 before tax" in result


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"effective_date": "2027-03-31", "expiry_date": "2026-09-15"},
            "effective_date must be earlier than expiry_date",
        ),
        ({"expiry_date": "2028-09-15"}, "more than one 365-day term"),
        ({"effective_date": "15/09/2026"}, "not a real calendar date"),
        ({"effective_date": "next Tuesday"}, "must be YYYY-MM-DD"),
        ({"discount_amount": 500}, "discount_amount can only reduce"),
        ({"current_annual_price": -1}, "must not be negative"),
    ],
)
def test_proration_refuses_invalid_input(
    default_day_basis: None, overrides: dict[str, object], reason: str
) -> None:
    values: dict[str, object] = {
        "scenario": "upgrade",
        "current_annual_price": 900,
        "new_annual_price": 1300,
        "effective_date": "2026-09-15",
        "expiry_date": "2027-03-31",
    }
    values.update(overrides)

    result = compute_proration(**values)  # type: ignore[arg-type]

    assert result.startswith("PRORATION NOT CALCULATED")
    assert reason in result


def test_proration_rejects_an_unsupported_day_basis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRORATION_DAY_BASIS", "360")

    result = compute_proration("upgrade", 900, 1300, "2026-09-15", "2027-03-31")

    assert "PRORATION_DAY_BASIS must be 364 or 365" in result


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2026-9-5", date(2026, 9, 5)), ("09/15/2026", date(2026, 9, 15))],
)
def test_parse_sales_date_accepts_iso_and_us_formats(value: str, expected: date) -> None:
    assert parse_sales_date(value) == expected
