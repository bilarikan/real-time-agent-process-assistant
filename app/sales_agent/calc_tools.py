"""Deterministic calculation and discount-note tools.

The discount codes, scenarios, and rules below are fictional placeholders. Replace
them with your organisation's own policy before real use.
"""

from __future__ import annotations

import os
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CENT = Decimal("0.01")
_ALLOWED_DISCOUNT_CODES = {
    "PRICE-FIX-UP",
    "PRORATE-DOWN",
    "MGR-DISCOUNT",
    "CAMPAIGN-DISCOUNT",
}
_PRORATION_CONCEPT = "/pricing-and-discounts/proration"
_DEFAULT_PRORATION_DAY_BASIS = 365
_PRORATION_DAY_BASES = {364, 365}
_PRORATION_SCENARIOS = {
    "upgrade": "Upgrade",
    "add users": "Upgrade",
    "add-on": "Add-On",
    "add on": "Add-On",
    "addon": "Add-On",
    "migration": "Migration",
    "migration credit": "Migration credit",
    "downgrade": "Downgrade",
    "cancellation": "Cancellation",
    "cancel": "Cancellation",
}
_UPGRADE_SCENARIOS = {"Upgrade", "Add-On"}
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def compute_installment_refund(order_total_before_tax: float, months_to_refund: int) -> str:
    """Calculate a monthly-installment-plan refund as total divided by 12 times months.

    The result also distinguishes refunding paid installments from clearing
    future installments.
    """
    total = _money_decimal(order_total_before_tax, "order_total_before_tax")
    if total < 0:
        raise ValueError("order_total_before_tax must not be negative")
    if isinstance(months_to_refund, float) and months_to_refund.is_integer():
        months_to_refund = int(months_to_refund)
    if isinstance(months_to_refund, bool) or not isinstance(months_to_refund, int):
        raise ValueError("months_to_refund must be a whole number")
    if not 1 <= months_to_refund <= 12:
        raise ValueError("months_to_refund must be between 1 and 12")

    monthly = total / Decimal(12)
    refund = (monthly * months_to_refund).quantize(_CENT, rounding=ROUND_HALF_UP)
    return "\n".join(
        [
            "INSTALLMENT REFUND CALCULATION",
            f"Order total before tax: {_currency(total)}",
            f"Formula: {_currency(total)} ÷ 12 × {months_to_refund}",
            f"Refund amount before tax: {_currency(refund)}",
            "",
            "Refund the calculated amount for paid installment(s). Clearing is separate: "
            "Sales Admin clears the unpaid remainder using the full order amount.",
            "For a cancellation, explain that one more monthly installment will be charged "
            "for the notice period unless the current month's charge already accounts for it.",
            "Concept ID: /pricing-and-discounts/installment-refunds",
        ]
    )


def compute_proration(
    scenario: str,
    current_annual_price: float,
    new_annual_price: float,
    effective_date: str,
    expiry_date: str,
    discount_amount: float = 0.0,
    system_order_price: float = 0.0,
) -> str:
    """Prorate an annual price change to the current expiry date, day by day.

    Prorated amount = (new_annual_price - current_annual_price - discount_amount)
    divided by the day basis (365 days by default) times the days remaining, where
    days remaining = expiry_date - effective_date. Prices are annual and before
    tax. Use current_annual_price=0 for an add-on, and new_annual_price=0 for a
    refund or migration credit. Dates are YYYY-MM-DD or MM/DD/YYYY. For a
    cancellation, effective_date is the call date plus the notice period.
    scenario: upgrade, add-on, migration, migration credit, downgrade, or
    cancellation. Optional: system_order_price (the order system's price before
    adjustment) gives the PRORATE-DOWN decrease.
    """
    try:
        basis = _proration_day_basis()
        current = _money_decimal(current_annual_price, "current_annual_price")
        new = _money_decimal(new_annual_price, "new_annual_price")
        discount = _money_decimal(discount_amount, "discount_amount")
        order_price = _money_decimal(system_order_price, "system_order_price")
        effective = parse_sales_date(effective_date, "effective_date")
        expiry = parse_sales_date(expiry_date, "expiry_date")
    except ValueError as exc:
        return _proration_refusal(str(exc))

    if min(current, new, discount, order_price) < 0:
        return _proration_refusal("prices, discount, and system order price must not be negative")
    if current == 0 and new == 0:
        return _proration_refusal("enter the current annual price, the new annual price, or both")
    days = (expiry - effective).days
    if days <= 0:
        return _proration_refusal("effective_date must be earlier than expiry_date")
    if days > basis:
        return _proration_refusal(
            f"the dates are {days} days apart, more than one {basis}-day term; "
            "check the expiry date"
        )

    difference = new - current
    if discount and discount > difference:
        return _proration_refusal(
            "discount_amount can only reduce a positive price difference, and not below zero"
        )
    chargeable = difference - discount
    prorated = (chargeable * days / basis).quantize(_CENT, rounding=ROUND_HALF_UP)
    daily_rate = (chargeable / basis).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    label = _PRORATION_SCENARIOS.get(
        " ".join(str(scenario).casefold().split()), str(scenario).strip() or "Unspecified"
    )

    discount_text = f" - {_currency(discount)} discount" if discount else ""
    formula = f"({_currency(new)} - {_currency(current)}{discount_text}) ÷ {basis} × {days}"
    return "\n".join(
        [
            "PRORATION CALCULATION",
            f"Scenario: {label}",
            f"Current annual price: {_currency(current)} before tax",
            f"New annual price: {_currency(new)} before tax",
            f"Annual difference{' after discount' if discount else ''}: "
            f"{_signed_currency(chargeable)}",
            f"Effective date: {_describe_date(effective)}",
            f"Expiry date: {_describe_date(expiry)}",
            f"Days remaining: {days} (expiry date - effective date)",
            f"Daily rate: {_signed_currency(chargeable)} ÷ {basis} = "
            f"{_signed_currency(daily_rate, places=6)}",
            f"Prorated amount: {formula} = {_signed_currency(prorated)} before tax",
            *_proration_guidance(label, prorated, order_price),
            f"Notes line: Proration: {formula} days ({effective.isoformat()} to "
            f"{expiry.isoformat()}) = {_signed_currency(prorated)} before tax",
            f"Basis: daily over a {basis}-day term; rounded once to the cent; before tax.",
            f"Concept ID: {_PRORATION_CONCEPT}",
        ]
    )


def build_discount_note(
    account_id: str,
    discount_type: str,
    original_amount: float,
    adjustment_amount: float,
    total_after_adjustment: float,
    adjustment_direction: str,
    date_of_call: str,
    time_of_call: str,
    phone_number: str,
    reason_for_discount: str,
    sales_matrix_explored: bool,
    discount_code: str,
    requesting_rep_id: str,
    campaign_code: str = "",
    system_has_issue: bool = False,
    manager_approval_attached: bool = False,
    proration_calculation: str = "",
    one_time_expectation_last_year: str = "not applicable",
    repeat_discount_reason: str = "not applicable",
    amount_paid_last_year: str = "not applicable",
    discount_received_last_year: str = "not applicable",
    set_one_time_expectation_now: bool = True,
) -> str:
    """Build a paste-ready discount note after validating code rules.

    The adjustment amount is always positive. Use adjustment_direction="increase"
    or "decrease" to describe how it changes the original amount.
    """
    missing = [
        name
        for name, value in {
            "account_id": account_id,
            "discount_type": discount_type,
            "date_of_call": date_of_call,
            "time_of_call": time_of_call,
            "phone_number": phone_number,
            "reason_for_discount": reason_for_discount,
            "requesting_rep_id": requesting_rep_id,
        }.items()
        if not str(value).strip()
    ]
    if missing:
        return _refusal(f"missing mandatory field(s): {', '.join(missing)}")

    reason = " ".join(reason_for_discount.split())
    if reason.casefold().strip(" .") == "price sensitive":
        return _refusal('"price sensitive" alone is not a sufficient discount reason')

    try:
        original = _money_decimal(original_amount, "original_amount")
        adjustment = _money_decimal(adjustment_amount, "adjustment_amount")
        final = _money_decimal(total_after_adjustment, "total_after_adjustment")
    except ValueError as exc:
        return _refusal(str(exc))

    if original <= 0:
        return _refusal("original_amount must be greater than zero")
    if adjustment <= 0:
        return _refusal("adjustment_amount must be greater than zero")

    direction = adjustment_direction.strip().casefold()
    if direction not in {"increase", "decrease"}:
        return _refusal('adjustment_direction must be "increase" or "decrease"')

    expected_total = original + adjustment if direction == "increase" else original - adjustment
    expected_total = expected_total.quantize(_CENT, rounding=ROUND_HALF_UP)
    if expected_total != final:
        return _refusal(
            "amounts do not reconcile: "
            f"{_currency(original)} {direction} by {_currency(adjustment)} "
            f"must total {_currency(expected_total)}"
        )

    code = _normalise_discount_code(discount_code)
    if code not in _ALLOWED_DISCOUNT_CODES:
        return _refusal(
            f"unsupported discount code {discount_code!r}; use a documented discount code"
        )

    rule_error = _validate_discount_code_rule(
        code=code,
        direction=direction,
        campaign_code=campaign_code,
        system_has_issue=system_has_issue,
        manager_approval_attached=manager_approval_attached,
        proration_calculation=proration_calculation,
    )
    if rule_error:
        return _refusal(rule_error)

    percent = (adjustment / original * Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return "\n".join(
        [
            "DISCOUNT APPROVAL / ORDER NOTES",
            f"Account ID: {account_id.strip()}",
            f"Type of discount: {discount_type.strip()}",
            f"Original amount before tax: {_currency(original)}",
            f"Percent adjusted: {percent}%",
            f"Amount adjusted: {_currency(adjustment)} ({direction})",
            f"Total after adjustment: {_currency(final)}",
            f"Date of call: {date_of_call.strip()}",
            f"Time of call: {time_of_call.strip()}",
            f"Phone number: {phone_number.strip()}",
            f"Reason for discount: {reason}",
            f"All prior sales-matrix options explored: {_yes_no(sales_matrix_explored)}",
            f"Discount code: {code}",
            f"Campaign code: {campaign_code.strip() or 'Not applicable'}",
            f"System issue present: {_yes_no(system_has_issue)}",
            f"One-time-only expectation given last year: {one_time_expectation_last_year.strip()}",
            f"Reason discount is repeated: {repeat_discount_reason.strip()}",
            f"Amount paid last year: {amount_paid_last_year.strip()}",
            f"Discount received last year: {discount_received_last_year.strip()}",
            f"One-time-only expectation set in this order: {_yes_no(set_one_time_expectation_now)}",
            f"Requesting rep ID: {requesting_rep_id.strip()}",
            f"Written manager approval attached: {_yes_no(manager_approval_attached)}",
            (
                f"Proration calculation: {proration_calculation.strip()}"
                if proration_calculation.strip()
                else "Proration calculation: Not applicable"
            ),
            "",
            "Attach the written approval and cart screenshot when applicable.",
            "Concept ID: /pricing-and-discounts/discount-codes",
        ]
    )


def parse_sales_date(value: object, field_name: str = "date") -> date:
    """Parse YYYY-MM-DD or MM/DD/YYYY; reject anything ambiguous."""
    text = str(value).strip()
    match = _ISO_DATE.match(text)
    if match:
        year, month, day = (int(part) for part in match.groups())
    else:
        match = _US_DATE.match(text)
        if not match:
            raise ValueError(f"{field_name} must be YYYY-MM-DD or MM/DD/YYYY: {text!r}")
        month, day, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a real calendar date: {text!r}") from exc


def _proration_day_basis() -> int:
    raw = os.getenv("PRORATION_DAY_BASIS", str(_DEFAULT_PRORATION_DAY_BASIS)).strip()
    if not raw.isdigit() or int(raw) not in _PRORATION_DAY_BASES:
        raise ValueError("PRORATION_DAY_BASIS must be 364 or 365")
    return int(raw)


def _proration_guidance(scenario: str, amount: Decimal, order_price: Decimal) -> list[str]:
    magnitude = _currency(abs(amount))
    if amount == 0:
        return ["Result: nothing to charge or refund."]
    if amount > 0:
        lines = [f"Result: charge {magnitude} before tax."]
        if scenario == "Migration":
            lines.append(
                "Positive migration amount: charge it on a proration order aligned "
                "to the current expiry date."
            )
        elif order_price > amount:
            lines.append(
                f"System order price {_currency(order_price)}: apply PRORATE-DOWN to decrease it "
                f"by {_currency(order_price - amount)} to {magnitude}, and paste the notes line."
            )
        elif order_price == amount:
            lines.append("The system's order price already matches the prorated amount.")
        elif order_price > 0:
            lines.append("The system's order price is below the prorated amount; check the order.")
        elif scenario in _UPGRADE_SCENARIOS:
            lines.append(
                "If the system shows the full price, apply PRORATE-DOWN to decrease it to this "
                "amount "
                "and paste the notes line."
            )
        return lines

    lines = [
        f"Result: prorated refund or credit of {magnitude} before tax (not a PRORATE-DOWN case)."
    ]
    if scenario == "Migration credit":
        lines.append(
            "Submit the migration credit memo for this amount with the service SKU, "
            "the notes line, and the migration reason in the comments."
        )
    elif scenario == "Migration":
        lines.append(
            "Negative migration amount: submit a credit memo request for this prorated "
            "refund, then create the new order for a full year."
        )
    elif scenario == "Cancellation":
        lines.append(
            "Refund from the effective date (call date plus the notice period); approval "
            "levels are in the refund policy."
        )
    else:
        lines.append(
            "Submit it as a credit memo refund request; approval levels are in the refund policy."
        )
    return lines


def _proration_refusal(reason: str) -> str:
    return "\n".join(
        [
            "PRORATION NOT CALCULATED",
            f"Reason: {reason}",
            "Correct the input and call compute_proration again. Do not estimate.",
        ]
    )


def _validate_discount_code_rule(
    *,
    code: str,
    direction: str,
    campaign_code: str,
    system_has_issue: bool,
    manager_approval_attached: bool,
    proration_calculation: str,
) -> str | None:
    if code == "PRICE-FIX-UP" and direction != "increase":
        return "PRICE-FIX-UP is only permitted to increase an incorrect system price"
    if code == "PRICE-FIX-UP" and system_has_issue:
        return "PRICE-FIX-UP cannot be used while the system has an issue; escalate first"
    if code == "PRORATE-DOWN":
        if direction != "decrease":
            return "PRORATE-DOWN is only permitted for a proration decrease"
        if not proration_calculation.strip():
            return "PRORATE-DOWN requires the approved proration calculation in the notes"
    if code == "MGR-DISCOUNT" and not manager_approval_attached:
        return "MGR-DISCOUNT requires attached written manager approval"
    if code == "CAMPAIGN-DISCOUNT" and not campaign_code.strip():
        return "CAMPAIGN-DISCOUNT must be paired with a campaign code"
    if code in {"MGR-DISCOUNT", "CAMPAIGN-DISCOUNT"} and direction != "decrease":
        return f"{code} is a discount and therefore must decrease the price"
    return None


def _normalise_discount_code(value: str) -> str:
    return value.strip().upper().replace(" ", "-").replace("_", "-")


def _money_decimal(value: float, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _currency(value: Decimal) -> str:
    return f"${value.quantize(_CENT, rounding=ROUND_HALF_UP):,.2f}"


def _signed_currency(value: Decimal, places: int = 2) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{places}f}"


def _describe_date(value: date) -> str:
    return f"{value.isoformat()} ({value:%a %d %b %Y})"


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _refusal(reason: str) -> str:
    return f"REFUSED — no discount note emitted.\nRule failed: {reason}"
