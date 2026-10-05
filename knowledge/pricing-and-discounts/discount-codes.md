---
type: Policy
title: Discount codes (placeholder)
description: Fictional discount and price-adjustment codes PRICE-FIX-UP, PRORATE-DOWN, MGR-DISCOUNT, and CAMPAIGN-DISCOUNT, with the rules enforced by build_discount_note.
tags: [discount, codes, price-fix-up, prorate-down, mgr-discount, campaign-discount, placeholder]
status: draft
generated:
  by: example
  at: 2026-01-01T00:00:00Z
---

# Discount codes (fictional)

| Code | Use | Rule |
|---|---|---|
| `PRICE-FIX-UP` | Correct an incorrect system price | Increase only; not while the system has a known issue |
| `PRORATE-DOWN` | Reduce an upgrade to its prorated amount | Decrease only; the approved proration calculation must be in the notes |
| `MGR-DISCOUNT` | Manager-approved discount | Decrease only; written manager approval must be attached |
| `CAMPAIGN-DISCOUNT` | Campaign promotion | Decrease only; must carry a campaign code |

Use `build_discount_note` to validate the request and produce a paste-ready note.
"Price sensitive" alone is not a sufficient reason.
