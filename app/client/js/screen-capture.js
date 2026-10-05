export class AdaptiveScreenCapture {
  constructor({
    preview,
    getSettings,
    onFrame,
    onStats = () => {},
    onStateChange = () => {},
  }) {
    this.preview = preview;
    this.getSettings = getSettings;
    this.onFrame = onFrame;
    this.onStats = onStats;
    this.onStateChange = onStateChange;
    this.stream = null;
    this.timer = null;
    this.captureCanvas = document.createElement("canvas");
    this.captureContext = this.captureCanvas.getContext("2d", { alpha: false });
    this.diffCanvas = document.createElement("canvas");
    this.diffCanvas.width = 32;
    this.diffCanvas.height = 32;
    this.diffContext = this.diffCanvas.getContext("2d", {
      alpha: false,
      willReadFrequently: true,
    });
    this.lastSentGreyscale = null;
    this.lastSentAt = 0;
    this.captured = 0;
    this.sent = 0;
    this.captureInProgress = false;
  }

  get active() {
    return Boolean(this.stream);
  }

  async start() {
    if (this.active) {
      return;
    }
    this.stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 2, max: 4 } },
      audio: false,
    });
    this.preview.srcObject = this.stream;
    await this.preview.play();

    this.lastSentGreyscale = null;
    this.lastSentAt = 0;
    this.captured = 0;
    this.sent = 0;
    this.#reportStats();

    const [track] = this.stream.getVideoTracks();
    track.addEventListener("ended", () => this.stop(), { once: true });
    this.timer = window.setInterval(() => void this.capture(), 1000);
    this.onStateChange(true);
    await this.capture(true);
  }

  async capture(force = false) {
    if (!this.active || this.preview.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      return false;
    }
    if (this.captureInProgress) {
      return false;
    }
    this.captureInProgress = true;

    try {
      const { width, height } = scaledDimensions(
        this.preview.videoWidth,
        this.preview.videoHeight,
        768,
      );
      this.captureCanvas.width = width;
      this.captureCanvas.height = height;
      this.captureContext.drawImage(this.preview, 0, 0, width, height);
      this.captured += 1;

      this.diffContext.drawImage(this.captureCanvas, 0, 0, 32, 32);
      const greyscale = toGreyscale(
        this.diffContext.getImageData(0, 0, 32, 32).data,
      );
      const difference = meanAbsoluteDifference(
        greyscale,
        this.lastSentGreyscale,
      );
      const now = performance.now();
      const settings = this.getSettings();
      const heartbeatDue =
        this.lastSentAt === 0 ||
        now - this.lastSentAt >= settings.frameHeartbeat * 1000;
      const changed = difference >= settings.changeThreshold;

      if (!force && !heartbeatDue && !changed) {
        this.#reportStats();
        return false;
      }

      const reason = force
        ? "explicit"
        : heartbeatDue
          ? "heartbeat"
          : "change";
      const blob = await canvasToBlob(this.captureCanvas, "image/jpeg", 0.72);
      await this.onFrame(blob, reason);
      this.lastSentGreyscale = greyscale;
      this.lastSentAt = now;
      this.sent += 1;
      this.#reportStats();
      return true;
    } finally {
      this.captureInProgress = false;
    }
  }

  stop() {
    window.clearInterval(this.timer);
    for (const track of this.stream?.getTracks() ?? []) {
      track.stop();
    }
    this.preview.pause();
    this.preview.srcObject = null;
    this.stream = null;
    this.timer = null;
    this.captureInProgress = false;
    this.onStateChange(false);
  }

  #reportStats() {
    this.onStats({ captured: this.captured, sent: this.sent });
  }
}

function scaledDimensions(width, height, maximum) {
  const scale = Math.min(maximum / width, maximum / height, 1);
  return {
    width: Math.max(Math.round(width * scale), 1),
    height: Math.max(Math.round(height * scale), 1),
  };
}

function toGreyscale(rgba) {
  const result = new Uint8Array(rgba.length / 4);
  for (let source = 0, target = 0; source < rgba.length; source += 4, target += 1) {
    result[target] = Math.round(
      rgba[source] * 0.299 + rgba[source + 1] * 0.587 + rgba[source + 2] * 0.114,
    );
  }
  return result;
}

function meanAbsoluteDifference(current, previous) {
  if (!previous || previous.length !== current.length) {
    return Number.POSITIVE_INFINITY;
  }
  let difference = 0;
  for (let index = 0; index < current.length; index += 1) {
    difference += Math.abs(current[index] - previous[index]);
  }
  return (difference / current.length / 255) * 100;
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Could not encode screen frame"))),
      type,
      quality,
    );
  });
}
