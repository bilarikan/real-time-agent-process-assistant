"""FastAPI bridge between the browser client and ADK ``Runner.run_live()``."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from starlette.websockets import WebSocketState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT = Path(__file__).resolve().parent / "client"
load_dotenv(PROJECT_ROOT / ".env")

from .live_config import build_live_run_config  # noqa: E402
from .sales_agent.okf_search_index import OKFError  # noqa: E402
from .sales_agent.okf_tools import (  # noqa: E402
    knowledge_bundle_root,
    okf_search,
    preload_knowledge_index,
)
from .session_budget import BudgetLimits, SessionBudget  # noqa: E402

LOGGER = logging.getLogger(__name__)
APP_NAME = "sales-agent"
LOCAL_USER_ID = "local-rep"
_AUDIO_MIME_TYPE = "audio/pcm;rate=16000"
_IMAGE_MIME_TYPE = "image/jpeg"
_MAX_IMAGE_BYTES = 2_000_000
_INPUT_PRICE_PER_MILLION = {
    "TEXT": 0.50,
    "AUDIO": 3.00,
    "IMAGE": 3.00,
    "VIDEO": 3.00,
}
_OUTPUT_PRICE_PER_MILLION = {
    "TEXT": 2.00,
    "AUDIO": 12.00,
}

session_service = InMemorySessionService()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    preload_knowledge_index()
    yield


app = FastAPI(
    title="Real-Time Sales Assistant",
    version="0.2.0",
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory=CLIENT_ROOT, check_dir=False),
    name="static",
)
app.mount(
    "/knowledge",
    StaticFiles(directory=knowledge_bundle_root(), check_dir=False),
    name="knowledge",
)


@app.get("/", include_in_schema=False)
def client() -> FileResponse:
    index = CLIENT_ROOT / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="browser client is not installed")
    return FileResponse(index)


@app.get("/health")
def health() -> dict[str, object]:
    index = preload_knowledge_index()
    return {
        "status": "ok",
        "knowledge_concepts": len(index.documents),
        "live_model_configured": not _missing_live_environment(),
        "live_websocket": "ready",
    }


@app.post("/session")
async def create_session() -> dict[str, object]:
    missing = _missing_live_environment()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"missing Live configuration: {', '.join(missing)}",
        )

    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=LOCAL_USER_ID,
        session_id=session_id,
        state={"prototype": True},
    )
    limits = BudgetLimits.from_env()
    return {
        "session_id": session_id,
        "user_id": LOCAL_USER_ID,
        "budget": {
            "seconds": limits.seconds,
            "tokens": limits.tokens,
            "turns": limits.turns,
        },
    }


@app.get("/api/knowledge/search")
def search_knowledge(
    q: str = Query(min_length=1),
    include_deprecated: bool = False,
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, str]:
    """Offline diagnostic endpoint; production answers still go through the agent."""
    try:
        results = okf_search(
            q,
            include_deprecated=include_deprecated,
            limit=limit,
        )
    except OKFError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"results": results}


@app.websocket("/live")
async def live(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = websocket.query_params.get("session_id", "")
    user_id = websocket.query_params.get("user_id", LOCAL_USER_ID)
    if not session_id:
        await _reject_websocket(websocket, "session_id is required", code=4400)
        return

    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        await _reject_websocket(websocket, "session not found", code=4404)
        return

    try:
        runner = _get_runner()
        run_config = build_live_run_config()
        budget = SessionBudget(BudgetLimits.from_env())
    except (RuntimeError, ValueError) as exc:
        await _reject_websocket(websocket, str(exc), code=4503)
        return

    live_queue = LiveRequestQueue()
    send_lock = asyncio.Lock()

    async def send_json(payload: dict[str, Any]) -> None:
        async with send_lock:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(payload)

    async def send_text(payload: str) -> None:
        async with send_lock:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(payload)

    async def upstream() -> None:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                return
            try:
                message = json.loads(raw)
                should_close = _forward_client_message(message, live_queue)
            except (ClientProtocolError, json.JSONDecodeError) as exc:
                await send_json({"serverEvent": "protocol_error", "message": str(exc)})
                continue
            if should_close:
                return

    async def downstream() -> None:
        usage_sequence = 0
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=live_queue,
            run_config=run_config,
        ):
            if event.usage_metadata and event.usage_metadata.total_token_count is not None:
                usage_sequence += 1
                event_id = event.id or f"usage-{usage_sequence}"
                budget.record_usage(
                    event_id,
                    event.usage_metadata.total_token_count,
                    estimated_cost_usd=_estimate_usage_cost(event.usage_metadata),
                )
            if event.turn_complete:
                budget.record_turn()

            await send_text(event.model_dump_json(exclude_none=True, by_alias=True))

            if event.usage_metadata or event.turn_complete:
                snapshot = budget.snapshot()
                await send_json({"serverEvent": "budget", **snapshot.as_dict()})
                if snapshot.exhausted:
                    await send_json(
                        {
                            "serverEvent": "budget_exhausted",
                            "message": "Session budget reached; Live input has stopped.",
                        }
                    )
                    live_queue.close()
                    return

    async def budget_monitor() -> None:
        last_reported = -1
        while True:
            await asyncio.sleep(1)
            snapshot = budget.snapshot()
            if snapshot.elapsed_seconds // 5 != last_reported:
                last_reported = snapshot.elapsed_seconds // 5
                await send_json({"serverEvent": "budget", **snapshot.as_dict()})
            if snapshot.exhausted:
                await send_json(
                    {
                        "serverEvent": "budget_exhausted",
                        "message": "Session time budget reached; Live input has stopped.",
                    }
                )
                live_queue.close()
                return

    await send_json(
        {
            "serverEvent": "connected",
            "sessionId": session_id,
            "audioInput": _AUDIO_MIME_TYPE,
            "audioOutput": "audio/pcm;rate=24000",
        }
    )

    tasks = {
        asyncio.create_task(upstream(), name="browser-upstream"),
        asyncio.create_task(downstream(), name="adk-downstream"),
        asyncio.create_task(budget_monitor(), name="budget-monitor"),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exception = task.exception()
            if exception:
                raise exception
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        LOGGER.exception("Live session %s failed", session_id)
        with suppress(RuntimeError, WebSocketDisconnect):
            await send_json({"serverEvent": "error", "message": _safe_error(exc)})
    finally:
        live_queue.close()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if websocket.client_state == WebSocketState.CONNECTED:
            with suppress(RuntimeError, WebSocketDisconnect):
                await websocket.close()


class ClientProtocolError(ValueError):
    """Raised when a browser message cannot be forwarded safely."""


def _forward_client_message(
    message: object,
    live_queue: LiveRequestQueue,
) -> Literal[True, False]:
    if not isinstance(message, dict):
        raise ClientProtocolError("message must be a JSON object")

    message_type = message.get("type")
    if message_type == "text":
        text = str(message.get("text", "")).strip()
        if not text:
            raise ClientProtocolError("text must not be empty")
        if len(text) > 4000:
            raise ClientProtocolError("text must not exceed 4000 characters")
        live_queue.send_content(types.Content(parts=[types.Part(text=text)]))
        return False

    if message_type == "audio":
        mime_type = str(message.get("mimeType", ""))
        if mime_type != _AUDIO_MIME_TYPE:
            raise ClientProtocolError(f"audio must use {_AUDIO_MIME_TYPE}")
        data = _decode_media(message.get("data"), maximum_bytes=1280)
        if len(data) not in {640, 1280}:
            raise ClientProtocolError("audio chunks must contain exactly 20 or 40 ms of PCM")
        live_queue.send_realtime(types.Blob(mime_type=mime_type, data=data))
        return False

    if message_type == "image":
        mime_type = str(message.get("mimeType", ""))
        if mime_type != _IMAGE_MIME_TYPE:
            raise ClientProtocolError(f"screen frames must use {_IMAGE_MIME_TYPE}")
        data = _decode_media(message.get("data"), maximum_bytes=_MAX_IMAGE_BYTES)
        live_queue.send_realtime(types.Blob(mime_type=mime_type, data=data))
        return False

    if message_type == "control":
        action = message.get("action")
        if action == "close":
            live_queue.close()
            return True
        if action == "audio_end":
            # The rep switched the microphone off. Flush buffered speech so the
            # Live API does not wait for an end of speech that never arrives.
            live_queue.send_audio_stream_end()
            return False
        raise ClientProtocolError(f"unsupported control action: {action!r}")

    raise ClientProtocolError(f"unsupported message type: {message_type!r}")


def _decode_media(value: object, *, maximum_bytes: int) -> bytes:
    if not isinstance(value, str) or not value:
        raise ClientProtocolError("media data must be non-empty base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ClientProtocolError("media data is not valid base64") from exc
    if len(decoded) > maximum_bytes:
        raise ClientProtocolError(f"media payload exceeds {maximum_bytes} bytes")
    return decoded


@lru_cache(maxsize=1)
def _get_runner() -> Runner:
    missing = _missing_live_environment()
    if missing:
        raise RuntimeError(f"missing Live configuration: {', '.join(missing)}")
    from .sales_agent.agent import root_agent

    return Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=session_service,
    )


def _missing_live_environment() -> list[str]:
    required = (
        "GOOGLE_GENAI_USE_ENTERPRISE",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "LIVE_MODEL_ID",
    )
    return [name for name in required if not os.getenv(name)]


async def _reject_websocket(websocket: WebSocket, message: str, *, code: int) -> None:
    await websocket.send_json({"serverEvent": "error", "message": message})
    await websocket.close(code=code)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "The Live API timed out."
    return f"{type(exc).__name__}: {exc}"


def _estimate_usage_cost(
    metadata: types.GenerateContentResponseUsageMetadata,
) -> float:
    """Estimate public-list-price cost from modality-specific token details."""

    def calculate(
        details: list[types.ModalityTokenCount] | None,
        prices: dict[str, float],
    ) -> float:
        total = 0.0
        for detail in details or []:
            modality = getattr(detail.modality, "value", detail.modality)
            token_count = detail.token_count or 0
            total += token_count * prices.get(str(modality), 0.0) / 1_000_000
        return total

    return calculate(
        metadata.prompt_tokens_details,
        _INPUT_PRICE_PER_MILLION,
    ) + calculate(
        metadata.candidates_tokens_details,
        _OUTPUT_PRICE_PER_MILLION,
    )


def main() -> None:
    import uvicorn

    # Auto-reload is for development only: saving a Python file restarts the
    # server and drops the live session.
    reload = os.getenv("SERVER_RELOAD", "false").strip().casefold() in {"1", "true", "yes", "on"}
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=reload)
