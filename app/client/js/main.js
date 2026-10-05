import { MicrophoneCapture } from "./audio-capture.js";
import { PcmPlayback } from "./audio-playback.js";
import { AdaptiveScreenCapture } from "./screen-capture.js";
import { LiveSession } from "./session.js";
import { bindSettings } from "./settings.js";
import { TranscriptView } from "./transcript.js";

const ui = {
  startButton: byId("startButton"),
  stopButton: byId("stopButton"),
  micButton: byId("micButton"),
  screenCheckButton: byId("screenCheckButton"),
  connectionStatus: byId("connectionStatus"),
  activityStatus: byId("activityStatus"),
  transcript: byId("transcript"),
  messageTemplate: byId("messageTemplate"),
  chatForm: byId("chatForm"),
  chatInput: byId("chatInput"),
  sendButton: byId("sendButton"),
  screenPreview: byId("screenPreview"),
  screenStatus: byId("screenStatus"),
  framesSent: byId("framesSent"),
  framesCaptured: byId("framesCaptured"),
  frameSavings: byId("frameSavings"),
  elapsedTime: byId("elapsedTime"),
  tokenCount: byId("tokenCount"),
  costEstimate: byId("costEstimate"),
  reconnectCount: byId("reconnectCount"),
  voiceOutput: byId("voiceOutput"),
  micEnabled: byId("micEnabled"),
  screenEnabled: byId("screenEnabled"),
  changeThreshold: byId("changeThreshold"),
  frameHeartbeat: byId("frameHeartbeat"),
  showToolCalls: byId("showToolCalls"),
};

let settings;
let running = false;
let micBusy = false;
const playback = new PcmPlayback();
const transcript = new TranscriptView({
  container: ui.transcript,
  template: ui.messageTemplate,
  showToolCalls: () => settings.showToolCalls,
});

const session = new LiveSession({
  onServerEvent: handleServerEvent,
  onAdkEvent: handleAdkEvent,
  onReconnect: (count) => {
    ui.reconnectCount.textContent = String(count);
    setConnection("connecting", "Reconnecting…");
  },
  onClose: () => {
    if (running && !session.intentionalClose) {
      setConnection("connecting", "Connection interrupted");
    }
  },
  onError: showError,
});

const microphone = new MicrophoneCapture({
  chunkMilliseconds: 40,
  onChunk: (chunk) => {
    if (!session.connected || !microphone.active) {
      return;
    }
    try {
      session.sendAudio(chunk);
    } catch (error) {
      showError(error);
    }
  },
  onStateChange: () => {
    updateMicButton();
    updateActivity();
  },
});

const screen = new AdaptiveScreenCapture({
  preview: ui.screenPreview,
  getSettings: () => settings,
  onFrame: async (blob, reason) => {
    await waitForConnection();
    await session.sendImage(blob, reason);
  },
  onStats: ({ captured, sent }) => {
    ui.framesCaptured.textContent = String(captured);
    ui.framesSent.textContent = String(sent);
    const savings = captured ? Math.round((1 - sent / captured) * 100) : 0;
    ui.frameSavings.textContent = `${Math.max(savings, 0)}%`;
  },
  onStateChange: (active) => {
    ui.screenStatus.textContent = active ? "Sharing" : "Off";
    ui.screenCheckButton.disabled = !running || !active;
    updateActivity();
  },
});

settings = bindSettings(
  {
    voiceOutput: ui.voiceOutput,
    micEnabled: ui.micEnabled,
    screenEnabled: ui.screenEnabled,
    changeThreshold: ui.changeThreshold,
    frameHeartbeat: ui.frameHeartbeat,
    showToolCalls: ui.showToolCalls,
  },
  (updated) => {
    Object.assign(settings, updated);
    void playback.setMuted(!settings.voiceOutput);
  },
);
void playback.setMuted(!settings.voiceOutput);
updateMicButton();

ui.startButton.addEventListener("click", startSession);
ui.stopButton.addEventListener("click", stopSession);
ui.micButton.addEventListener("click", toggleMicrophone);
ui.screenCheckButton.addEventListener("click", checkScreen);
ui.chatForm.addEventListener("submit", sendTypedMessage);
ui.chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    ui.chatForm.requestSubmit();
  }
});
window.addEventListener("beforeunload", () => {
  microphone.stop();
  screen.stop();
  session.stop();
});

async function startSession() {
  if (running) {
    return;
  }
  running = true;
  setControls(false);
  setConnection("connecting", "Connecting…");
  ui.activityStatus.textContent = "Requesting permissions…";
  transcript.reset();

  const sessionPromise = session.start();
  const microphonePromise = settings.micEnabled
    ? microphone.start().catch((error) => {
        transcript.addSystem(`Microphone unavailable, so typed chat only: ${error.message}`);
      })
    : Promise.resolve();
  const screenPromise = settings.screenEnabled
    ? screen.start().catch((error) => {
        transcript.addSystem(`Screen sharing unavailable: ${error.message}`);
      })
    : Promise.resolve();

  try {
    await Promise.all([sessionPromise, microphonePromise, screenPromise]);
    setControls(true);
    setConnection("live", "Live");
    if (!microphone.active) {
      transcript.addSystem(
        "Microphone off: the assistant does not hear the call. Type questions, or turn the microphone on.",
      );
    }
    updateActivity();
    ui.chatInput.focus();
  } catch (error) {
    showError(error);
    stopSession();
  }
}

function stopSession() {
  running = false;
  microphone.stop();
  screen.stop();
  playback.interrupt();
  session.stop();
  setControls(false, true);
  setConnection("idle", "Session stopped");
  ui.activityStatus.textContent = "Microphone and screen are off.";
}

async function toggleMicrophone() {
  if (!running || micBusy) {
    return;
  }
  micBusy = true;
  updateMicButton();
  try {
    if (microphone.active) {
      microphone.stop();
      if (session.connected) {
        session.sendAudioStreamEnd();
      }
      transcript.finishCallAudio();
      transcript.addSystem(
        "Microphone off: the assistant no longer hears the call. Type your questions.",
      );
      ui.chatInput.focus();
    } else {
      await microphone.start();
      transcript.addSystem("Microphone on: the assistant hears the call again.");
    }
  } catch (error) {
    showError(error);
  } finally {
    micBusy = false;
    updateMicButton();
    updateActivity();
  }
}

async function checkScreen() {
  if (!screen.active || !session.connected) {
    return;
  }
  ui.screenCheckButton.disabled = true;
  try {
    await screen.capture(true);
    playback.interrupt();
    transcript.markInterrupted();
    transcript.addTyped("Assistant, inspect the latest screen and flag the next action.");
    session.sendText(
      "Assistant, inspect the latest screen and flag any order-entry error, policy risk, or next action.",
    );
  } catch (error) {
    showError(error);
  } finally {
    ui.screenCheckButton.disabled = !running || !screen.active;
  }
}

function sendTypedMessage(event) {
  event.preventDefault();
  const text = ui.chatInput.value.trim();
  if (!text || !session.connected) {
    return;
  }
  playback.interrupt();
  transcript.markInterrupted();
  transcript.addTyped(text);
  try {
    session.sendText(text);
    ui.chatInput.value = "";
  } catch (error) {
    showError(error);
  }
}

function handleServerEvent(event) {
  if (event.serverEvent === "connected") {
    setConnection("live", "Live");
    return;
  }
  if (event.serverEvent === "budget") {
    ui.elapsedTime.textContent = formatElapsed(event.elapsedSeconds ?? 0);
    ui.tokenCount.textContent = Number(event.cumulativeTokens ?? 0).toLocaleString();
    ui.costEstimate.textContent = `$${Number(event.estimatedCostUsd ?? 0).toFixed(4)}`;
    if (event.warning) {
      ui.activityStatus.textContent = "Session budget is above 80%.";
    }
    return;
  }
  if (event.serverEvent === "budget_exhausted") {
    transcript.addSystem(event.message);
    stopSession();
    return;
  }
  if (event.serverEvent === "protocol_error" || event.serverEvent === "error") {
    showError(new Error(event.message));
  }
}

function handleAdkEvent(event) {
  if (event.interrupted) {
    playback.interrupt();
  }
  for (const part of event.content?.parts ?? []) {
    const media = part.inlineData;
    if (media?.data && media.mimeType?.startsWith("audio/")) {
      void playback.enqueue(media.data, media.mimeType).catch(showError);
    }
  }
  transcript.handleAdkEvent(event);
}

function setControls(active, reset = false) {
  ui.startButton.disabled = active || (!reset && running);
  ui.stopButton.disabled = !active;
  ui.chatInput.disabled = !active;
  ui.sendButton.disabled = !active;
  ui.screenCheckButton.disabled = !active || !screen.active;
  updateMicButton();
}

function updateMicButton() {
  const on = microphone.active;
  ui.micButton.setAttribute("aria-pressed", String(on));
  ui.micButton.textContent = on ? "Microphone on — turn off" : "Microphone off — turn on";
  ui.micButton.title = on
    ? "Stop the assistant hearing the call and switch to typed questions"
    : "Let the assistant hear the call again";
  ui.micButton.disabled = !running || micBusy || ui.stopButton.disabled;
}

function setConnection(state, text) {
  ui.connectionStatus.dataset.state = state;
  ui.connectionStatus.lastElementChild.textContent = text;
}

function updateActivity() {
  if (!running) {
    return;
  }
  const inputs = [
    microphone.active ? "microphone streaming" : "microphone off (typing only)",
    screen.active ? "screen sharing" : "screen off",
    settings.voiceOutput ? "voice audible" : "voice discarded",
  ];
  ui.activityStatus.textContent = inputs.join(" · ");
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  setConnection("error", "Needs attention");
  ui.activityStatus.textContent = message;
  transcript.addSystem(`Error: ${message}`);
}

async function waitForConnection() {
  const deadline = performance.now() + 12_000;
  while (!session.connected && performance.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 50));
  }
  if (!session.connected) {
    throw new Error("Screen frame could not be sent before the connection timeout");
  }
}

function formatElapsed(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function byId(id) {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing UI element #${id}`);
  }
  return element;
}
