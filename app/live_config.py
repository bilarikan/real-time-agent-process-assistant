"""Verified-at-import construction of the ADK 2.8 Live run configuration."""

from __future__ import annotations

import os

from google.adk.agents.run_config import RunConfig
from google.genai import types


def build_live_run_config() -> RunConfig:
    """Create the PRD-specified audio/transcription/resumption configuration."""
    return RunConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(language_codes=["en-CA"]),
        output_audio_transcription=types.AudioTranscriptionConfig(language_codes=["en-CA"]),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                end_of_speech_sensitivity=_end_of_speech_sensitivity(),
            ),
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
        session_resumption=types.SessionResumptionConfig(transparent=True),
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=16000,
            sliding_window=types.SlidingWindow(target_tokens=8000),
        ),
        proactivity=types.ProactivityConfig(proactive_audio=True),
        save_input_blobs_as_artifacts=False,
        save_live_blob=_boolean_env("SAVE_LIVE_BLOB", default=False),
    )


def _end_of_speech_sensitivity() -> types.EndSensitivity:
    configured = os.getenv("LIVE_END_OF_SPEECH_SENSITIVITY", "END_SENSITIVITY_HIGH").upper()
    allowed_values = {item.value for item in types.EndSensitivity}
    if configured not in allowed_values:
        allowed = ", ".join(item.value for item in types.EndSensitivity)
        raise ValueError(f"LIVE_END_OF_SPEECH_SENSITIVITY must be one of: {allowed}")
    return types.EndSensitivity(configured)


def _boolean_env(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalised = value.strip().casefold()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")
