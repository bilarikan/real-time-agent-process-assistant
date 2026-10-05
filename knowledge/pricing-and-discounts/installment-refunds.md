---
type: Policy
title: Installment-plan refunds (placeholder)
description: Fictional refund rule for monthly-installment orders — order total divided by 12 times the months refunded, with clearing handled separately.
tags: [refund, installment, monthly, clearing, placeholder]
status: draft
generated:
  by: example
  at: 2026-01-01T00:00:00Z
---

# Installment refunds (fictional)

Refund = order total before tax ÷ 12 × months to refund.

Refund the calculated amount for paid installments. Clearing the unpaid
remainder is a separate step done by an administrator. Use
`compute_installment_refund` for the figure.
