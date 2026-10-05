const STORAGE_KEY = "sales-assistant.settings.v1";

const DEFAULTS = Object.freeze({
  voiceOutput: false,
  micEnabled: true,
  screenEnabled: true,
  changeThreshold: 3,
  frameHeartbeat: 10,
  showToolCalls: true,
});

export function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    return sanitise({ ...DEFAULTS, ...saved });
  } catch {
    return { ...DEFAULTS };
  }
}

export function bindSettings(elements, onChange = () => {}) {
  const settings = loadSettings();
  writeControls(elements, settings);

  const update = () => {
    Object.assign(settings, readControls(elements));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    onChange({ ...settings });
  };

  for (const element of Object.values(elements)) {
    element.addEventListener("change", update);
  }

  return settings;
}

function writeControls(elements, settings) {
  elements.voiceOutput.checked = settings.voiceOutput;
  elements.micEnabled.checked = settings.micEnabled;
  elements.screenEnabled.checked = settings.screenEnabled;
  elements.changeThreshold.value = String(settings.changeThreshold);
  elements.frameHeartbeat.value = String(settings.frameHeartbeat);
  elements.showToolCalls.checked = settings.showToolCalls;
}

function readControls(elements) {
  return sanitise({
    voiceOutput: elements.voiceOutput.checked,
    micEnabled: elements.micEnabled.checked,
    screenEnabled: elements.screenEnabled.checked,
    changeThreshold: Number(elements.changeThreshold.value),
    frameHeartbeat: Number(elements.frameHeartbeat.value),
    showToolCalls: elements.showToolCalls.checked,
  });
}

function sanitise(value) {
  return {
    voiceOutput: Boolean(value.voiceOutput),
    micEnabled: value.micEnabled !== false,
    screenEnabled: value.screenEnabled !== false,
    changeThreshold: clampNumber(value.changeThreshold, 0.5, 25, 3),
    frameHeartbeat: clampNumber(value.frameHeartbeat, 3, 60, 10),
    showToolCalls: value.showToolCalls !== false,
  };
}

function clampNumber(value, minimum, maximum, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return fallback;
  }
  return Math.min(Math.max(number, minimum), maximum);
}
