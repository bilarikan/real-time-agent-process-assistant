# Start the demo

This procedure starts the local sales-assistant demo on a clean machine.

## 1. Prerequisites

- Python 3.11+, `uv`, Node.js, and the Google Cloud CLI
- a Google Cloud project with the Vertex AI API enabled
- a shared microphone and a Chrome-based browser

Use fabricated customer information only. Audio and shared-screen frames are
sent to the configured Google Cloud region.

## 2. Authenticate

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

## 3. Configure and install

```bash
cp .env.example .env     # set GOOGLE_CLOUD_PROJECT
uv sync --extra dev --extra build
```

`PRORATION_DAY_BASIS` selects 365 (default) or 364 days for proration.

## 4. Check, then start

```bash
uv run python tools/okf_build/validate.py knowledge
uv run pytest
npm test
uv run sales-assistant
```

## 5. Rehearse

1. Open http://127.0.0.1:8000 and select **Start session**.
2. Grant microphone and screen permissions; share the order-system window or tab,
   not the whole screen.
3. Ask: "What is the SKU for Acme Suite Plus annual?" — expect `ACME-PLUS-A`,
   cited from `/skus/acme-suite-plans`.
4. Ask for a proration, for example an upgrade from $900 to $1,300 expiring
   2027-03-31 effective 2026-09-15 — expect $215.89 before tax.
5. Use **Check my screen** before asking about an on-screen error.

## Troubleshooting

- `/health` reports the bundle size and Live readiness.
- If the session ends, restart the server and select the window again.
- A minimized window stops producing screen frames.
