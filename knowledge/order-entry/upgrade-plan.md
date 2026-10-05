---
type: Procedure
title: Upgrade a plan mid-term (placeholder)
description: Fictional procedure for upgrading a customer to a higher plan mid-term, using the proration tool and the PRORATE-DOWN price adjustment.
tags: [order-entry, upgrade, proration, prorate-down, placeholder]
status: draft
generated:
  by: example
  at: 2026-01-01T00:00:00Z
---

# Upgrade a plan (fictional)

1. Run `compute_proration` with the current and new annual prices and the
   customer's expiry date. See [Proration](/pricing-and-discounts/proration.md).
2. Create the upgrade order from the account's subscription list.
3. If the system shows the full price, apply `PRORATE-DOWN` to bring it to the
   prorated amount and paste the notes line the tool returns.
4. Run the [order checklist](/system-navigation/order-checklist.md) and save.
