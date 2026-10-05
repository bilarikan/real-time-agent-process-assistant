# Real-time process assistant

A local prototype of a real-time, voice-and-screen assistant for sales
representatives. It listens to a sales call, watches the rep's screen, and
whispers short, sourced answers to the rep (never to the customer).

## New to AI agents? Start here

**An AI agent** is a language model that does more than chat: it can decide to
call *tools* (look something up, run a calculation) and then use the results to
answer. This project has one agent with two kinds of tools:

1. **Knowledge tools** that search and read a folder of Markdown files
   (`knowledge/`). The agent is instructed to answer *only* from those files, and
   to cite which ones it used. This approach is often called *grounding*, and it
   keeps the model from making up prices, codes, or policy.
2. **Calculation tools** (refunds, proration, discount notes). Language models
   are unreliable at arithmetic, so the maths is done by ordinary, tested Python
   code and the agent just repeats the result.

**Live API.** Instead of typing and waiting, the browser streams microphone audio
and screenshots to the model (Google's Gemini Live, driven through the
[Agent Development Kit](https://google.github.io/adk-docs/), or ADK) and gets
text and speech back in real time.

**How a request flows:**

```
microphone + screen + typed chat  →  browser  →  FastAPI server  →  ADK agent
                                                                      │  ├─ knowledge tools → knowledge/*.md
                                                                      │  └─ calculation tools
                                       transcript + citations  ←──────┘
```

You do not need machine-learning experience to run or adapt this. If you can edit
Markdown and run a few terminal commands, you can swap in your own knowledge.

> **Placeholder content.** The knowledge bundle (`knowledge/`) describes a
> fictional vendor, "Acme", and its invented products, codes, and policies. The
> `grounding/` folder is empty. Replace both with your own material. This is a
> prototype, not a production system.

## Documentation

- [Project overview and design](docs/PROJECT_OVERVIEW.md)
- [Start the demo from scratch](docs/START_DEMO.md)
- [Product requirements template](docs/PRD.md)
- [Authoring the knowledge bundle](docs/AUTHORING_KNOWLEDGE.md)

## What is implemented

- OKF v0.2 document loading, path-safe reads, bounded tool responses, and local
  BM25-style search with exact-code boosting
- calculation tools: installment-plan refunds, discount-note validation with
  placeholder codes, daily proration, and a general exact calculator
- tool failures returned to the model instead of ending the live session
- the ADK agent definition and system instruction
- FastAPI session and `/live` WebSocket bridge using `Runner.run_live()`
- one-microphone 16 kHz mono capture in exact 40 ms PCM chunks, with a
  mid-session microphone switch for typed-only work
- adaptive 768 px screen sharing, typed chat, streaming transcription, citation
  chips, and client-side 24 kHz playback muted by default
- wall-clock, token, and model-turn budget telemetry
- an OKF validator and unit tests

## Set up

Requirements: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Node.js (for the
client tests), and Google Cloud Application Default Credentials for Live API work.

```bash
uv sync --extra dev --extra build
cp .env.example .env   # then set GOOGLE_CLOUD_PROJECT
uv run python tools/okf_build/validate.py knowledge
uv run pytest
npm test
uv run sales-assistant
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), select **Start session**,
and grant microphone and screen permissions. Use a shared room/USB microphone,
say “Assistant” before spoken requests, and use typed chat for critical beats.
Shared speech is labelled **Call audio** because the Live API does not provide
reliable speaker diarization.

The server also exposes `/health` and the offline diagnostic endpoint
`/api/knowledge/search?q=ACME-PLUS-A`.

For first-time Google Cloud setup:

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

Do not use real customer data. This prototype sends microphone audio and shared
screen frames to the configured Google Cloud region (`us-east1` by default).

## Repository layout

- `app/server.py` — FastAPI application and Live WebSocket bridge
- `app/live_config.py` — ADK Live configuration
- `app/sales_agent/` — agent instruction, knowledge tools, proration and
  discount tools, and the general calculator
- `app/client/` — browser interface and media pipeline
- `knowledge/` — OKF bundle (placeholder content)
- `grounding/` — your source documents (empty)
- `tools/okf_build/` — bundle validation tooling
- `tests/` — Python and browser regression tests

## Licence

[MIT](LICENSE). All company, product, SKU, and policy names in this repository
are fictional placeholders.
