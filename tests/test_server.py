from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.genai import types

from app.sales_agent.okf_tools import reset_knowledge_index_cache
from app.server import (
    ClientProtocolError,
    _estimate_usage_cost,
    _forward_client_message,
    app,
)

ROOT = Path(__file__).resolve().parents[1]


def _concept_count() -> int:
    return sum(
        path.name not in {"index.md", "log.md"} for path in (ROOT / "knowledge").rglob("*.md")
    )


@pytest.fixture
def live_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-east1")
    monkeypatch.setenv("LIVE_MODEL_ID", "test-live-model")


def test_health_offline_search_and_client(
    monkeypatch: pytest.MonkeyPatch,
    live_environment: None,
) -> None:
    monkeypatch.setenv("KNOWLEDGE_BUNDLE_PATH", str(ROOT / "knowledge"))
    reset_knowledge_index_cache()

    with TestClient(app) as client:
        health = client.get("/health")
        search = client.get("/api/knowledge/search", params={"q": "ACME-PLUS-A"})
        page = client.get("/")
        citation = client.get("/knowledge/skus/acme-suite-plans.md")
        navigation = client.get("/knowledge/system-navigation/screen-map.md")

    assert health.status_code == 200
    assert health.json()["knowledge_concepts"] == _concept_count()
    assert health.json()["live_websocket"] == "ready"
    assert health.json()["live_model_configured"] is True
    assert search.status_code == 200
    assert "/skus/acme-suite-plans" in search.json()["results"]
    assert page.status_code == 200
    assert "Live sales assistant" in page.text
    assert 'id="micButton"' in page.text
    assert citation.status_code == 200
    assert "ACME-PLUS-A" in citation.text
    assert navigation.status_code == 200


def test_create_session_returns_budget(live_environment: None) -> None:
    with TestClient(app) as client:
        response = client.post("/session")

    assert response.status_code == 200
    assert response.json()["user_id"] == "local-rep"
    assert response.json()["session_id"]
    assert response.json()["budget"]["seconds"] > 0


def test_unknown_websocket_session_is_rejected(live_environment: None) -> None:
    with (
        TestClient(app) as client,
        client.websocket_connect("/live?session_id=missing") as websocket,
    ):
        event = websocket.receive_json()

    assert event == {"serverEvent": "error", "message": "session not found"}


def test_client_protocol_forwards_text_and_audio() -> None:
    queue = FakeLiveQueue()

    assert _forward_client_message({"type": "text", "text": " hello "}, queue) is False
    assert (
        _forward_client_message(
            {
                "type": "audio",
                "mimeType": "audio/pcm;rate=16000",
                "data": base64.b64encode(bytes(1280)).decode(),
            },
            queue,
        )
        is False
    )

    assert queue.content[0].parts[0].text == "hello"
    assert queue.blobs[0].mime_type == "audio/pcm;rate=16000"
    assert len(queue.blobs[0].data) == 1280


def test_client_protocol_rejects_wrong_audio_chunk_size() -> None:
    with pytest.raises(ClientProtocolError, match="20 or 40 ms"):
        _forward_client_message(
            {
                "type": "audio",
                "mimeType": "audio/pcm;rate=16000",
                "data": base64.b64encode(bytes(100)).decode(),
            },
            FakeLiveQueue(),
        )


def test_client_protocol_ends_the_audio_stream_when_the_mic_is_switched_off() -> None:
    queue = FakeLiveQueue()

    assert _forward_client_message({"type": "control", "action": "audio_end"}, queue) is False
    assert queue.audio_stream_ended is True
    assert queue.closed is False
    assert _forward_client_message({"type": "control", "action": "close"}, queue) is True
    assert queue.closed is True
    with pytest.raises(ClientProtocolError, match="unsupported control action"):
        _forward_client_message({"type": "control", "action": "reboot"}, queue)


def test_usage_cost_estimate_uses_modality_rates() -> None:
    metadata = types.GenerateContentResponseUsageMetadata(
        prompt_tokens_details=[
            types.ModalityTokenCount(modality=types.MediaModality.TEXT, token_count=1000),
            types.ModalityTokenCount(modality=types.MediaModality.IMAGE, token_count=258),
        ],
        candidates_tokens_details=[
            types.ModalityTokenCount(modality=types.MediaModality.AUDIO, token_count=2000)
        ],
    )

    assert _estimate_usage_cost(metadata) == pytest.approx(0.025274)


class FakeLiveQueue:
    def __init__(self) -> None:
        self.content = []
        self.blobs = []
        self.audio_stream_ended = False
        self.closed = False

    def send_content(self, content) -> None:
        self.content.append(content)

    def send_realtime(self, blob) -> None:
        self.blobs.append(blob)

    def send_audio_stream_end(self) -> None:
        self.audio_stream_ended = True

    def close(self) -> None:
        self.closed = True
