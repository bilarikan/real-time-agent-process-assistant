export class MicrophoneCapture {
  constructor({ chunkMilliseconds = 40, onChunk, onStateChange = () => {} }) {
    this.chunkMilliseconds = chunkMilliseconds;
    this.onChunk = onChunk;
    this.onStateChange = onStateChange;
    this.stream = null;
    this.context = null;
    this.source = null;
    this.worklet = null;
    this.silentGain = null;
  }

  get active() {
    return Boolean(this.stream);
  }

  async start() {
    if (this.active) {
      return;
    }
    try {
      await this.#open();
    } catch (error) {
      this.stop();
      throw error;
    }
  }

  async #open() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    });

    const AudioContext = window.AudioContext ?? window.webkitAudioContext;
    this.context = new AudioContext({ latencyHint: "interactive" });
    await this.context.audioWorklet.addModule("/static/js/audio-worklet.js");
    await this.context.resume();

    this.source = this.context.createMediaStreamSource(this.stream);
    this.worklet = new AudioWorkletNode(this.context, "pcm-capture", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      channelCount: 1,
      processorOptions: { chunkMilliseconds: this.chunkMilliseconds },
    });
    this.silentGain = this.context.createGain();
    this.silentGain.gain.value = 0;
    this.worklet.port.onmessage = (event) => this.onChunk(event.data);

    this.source.connect(this.worklet);
    this.worklet.connect(this.silentGain);
    this.silentGain.connect(this.context.destination);

    for (const track of this.stream.getAudioTracks()) {
      track.addEventListener("ended", () => this.stop(), { once: true });
    }
    this.onStateChange(true);
  }

  stop() {
    this.worklet?.disconnect();
    this.source?.disconnect();
    this.silentGain?.disconnect();
    for (const track of this.stream?.getTracks() ?? []) {
      track.stop();
    }
    void this.context?.close();

    this.stream = null;
    this.context = null;
    this.source = null;
    this.worklet = null;
    this.silentGain = null;
    this.onStateChange(false);
  }
}
