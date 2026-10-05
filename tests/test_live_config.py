from __future__ import annotations

import pytest
from google.genai import types

from app.live_config import build_live_run_config


def test_live_config_matches_audio_only_prd_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIVE_END_OF_SPEECH_SENSITIVITY", raising=False)
    monkeypatch.delenv("SAVE_LIVE_BLOB", raising=False)

    config = build_live_run_config()

    assert config.response_modalities == [types.Modality.AUDIO]
    assert config.input_audio_transcription.language_codes == ["en-CA"]
    assert config.output_audio_transcription.language_codes == ["en-CA"]
    assert config.session_resumption.transparent is True
    assert config.context_window_compression.trigger_tokens == 16000
    assert config.context_window_compression.sliding_window.target_tokens == 8000
    assert config.proactivity.proactive_audio is True
    assert (
        config.realtime_input_config.turn_coverage == types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY
    )
    assert (
        config.realtime_input_config.automatic_activity_detection.end_of_speech_sensitivity
        == types.EndSensitivity.END_SENSITIVITY_HIGH
    )
    assert config.save_live_blob is False


def test_live_config_rejects_invalid_sensitivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVE_END_OF_SPEECH_SENSITIVITY", "fast-ish")

    with pytest.raises(ValueError, match="LIVE_END_OF_SPEECH_SENSITIVITY"):
        build_live_run_config()
