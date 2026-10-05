# Product requirements (template)

Fill this in for your own deployment.

## 1. Problem and users

- Who is the representative, and what call workflow do they follow?
- Which decisions or lookups slow them down or cause errors?

## 2. Scope

- Questions the assistant must answer (SKUs, pricing, discounts, refunds, process).
- Procedures it must walk through in the order system.
- Calculations it must perform deterministically.
- Explicit non-goals (it advises only; no tax, accounting, or legal advice).

## 3. Grounding

- Source documents and owners.
- Review gate before a concept may be marked human-verified.
- How retired guidance is superseded.

## 4. Privacy and deployment

- Data sent to the model (audio, screen frames), region, retention.
- Prohibited data (for example payment card numbers, real customer data).

## 5. Success measures and tests

- Accuracy, latency, cost per session, and the scenarios used to rehearse.
