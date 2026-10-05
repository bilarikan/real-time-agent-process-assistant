export class PcmPlayback {
  constructor() {
    this.muted = true;
    this.context = null;
    this.nextStartTime = 0;
    this.sources = new Set();
  }

  async setMuted(muted) {
    this.muted = muted;
    if (muted) {
      this.interrupt();
      return;
    }
    await this.#ensureContext();
    await this.context.resume();
  }

  async enqueue(base64Data, mimeType = "audio/pcm;rate=24000") {
    if (this.muted) {
      return;
    }
    await this.#ensureContext();

    const bytes = base64ToBytes(base64Data);
    const sampleRate = sampleRateFromMimeType(mimeType);
    const frameCount = Math.floor(bytes.byteLength / 2);
    if (!frameCount) {
      return;
    }

    const audioBuffer = this.context.createBuffer(1, frameCount, sampleRate);
    const output = audioBuffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let index = 0; index < frameCount; index += 1) {
      output[index] = view.getInt16(index * 2, true) / 0x8000;
    }

    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);
    source.addEventListener(
      "ended",
      () => {
        source.disconnect();
        this.sources.delete(source);
      },
      { once: true },
    );

    const now = this.context.currentTime;
    const startAt = Math.max(now + 0.015, this.nextStartTime);
    source.start(startAt);
    this.nextStartTime = startAt + audioBuffer.duration;
    this.sources.add(source);
  }

  interrupt() {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // A source can finish between iteration and stop().
      }
    }
    this.sources.clear();
    this.nextStartTime = this.context?.currentTime ?? 0;
  }

  async #ensureContext() {
    if (this.context) {
      return;
    }
    const AudioContext = window.AudioContext ?? window.webkitAudioContext;
    this.context = new AudioContext({ sampleRate: 24000, latencyHint: "interactive" });
    await this.context.resume();
  }
}

export function base64ToBytes(value) {
  const standardBase64 = value.replaceAll("-", "+").replaceAll("_", "/");
  const paddedBase64 = standardBase64.padEnd(
    Math.ceil(standardBase64.length / 4) * 4,
    "=",
  );
  const binary = atob(paddedBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function sampleRateFromMimeType(mimeType) {
  const match = /rate=(\d+)/i.exec(mimeType);
  return match ? Number(match[1]) : 24000;
}
