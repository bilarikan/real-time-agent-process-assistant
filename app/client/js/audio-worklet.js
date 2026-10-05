class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetSampleRate = 16000;
    this.chunkMilliseconds = options.processorOptions?.chunkMilliseconds ?? 40;
    this.chunkSamples = Math.round(
      (this.targetSampleRate * this.chunkMilliseconds) / 1000,
    );
    this.sourcePerTargetSample = sampleRate / this.targetSampleRate;
    this.inputBuffer = [];
    this.inputPosition = 0;
    this.outputBuffer = [];
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel?.length) {
      return true;
    }

    for (let index = 0; index < channel.length; index += 1) {
      this.inputBuffer.push(channel[index]);
    }
    this.#resample();
    this.#emitChunks();
    return true;
  }

  #resample() {
    while (this.inputPosition + 1 < this.inputBuffer.length) {
      const lowerIndex = Math.floor(this.inputPosition);
      const fraction = this.inputPosition - lowerIndex;
      const lower = this.inputBuffer[lowerIndex];
      const upper = this.inputBuffer[lowerIndex + 1];
      this.outputBuffer.push(lower + (upper - lower) * fraction);
      this.inputPosition += this.sourcePerTargetSample;
    }

    const consumed = Math.min(
      Math.floor(this.inputPosition),
      this.inputBuffer.length - 1,
    );
    if (consumed > 0) {
      this.inputBuffer.splice(0, consumed);
      this.inputPosition -= consumed;
    }
  }

  #emitChunks() {
    while (this.outputBuffer.length >= this.chunkSamples) {
      const samples = this.outputBuffer.splice(0, this.chunkSamples);
      const pcm = new Int16Array(samples.length);
      for (let index = 0; index < samples.length; index += 1) {
        const sample = Math.max(-1, Math.min(1, samples[index]));
        pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
