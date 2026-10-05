---
type: Policy
title: Proration rule (placeholder)
description: Fictional daily proration rule for upgrades, add-ons, migrations, downgrades, and cancellations, implemented by compute_proration.
tags: [proration, upgrade, add-on, migration, downgrade, cancellation, daily, placeholder]
status: draft
generated:
  by: example
  at: 2026-01-01T00:00:00Z
---

# Proration (fictional)

prorated amount = (new annual price − current annual price − any dollar
discount) ÷ day basis × days remaining

- days remaining = expiry date − effective date
- the day basis is 365 by default (`PRORATION_DAY_BASIS` may be 364 or 365)
- amounts are before tax and rounded once, to the cent
- a negative result is a prorated refund or credit
- for a cancellation, the effective date is the call date plus the notice period

Always use `compute_proration`; never calculate by hand.
