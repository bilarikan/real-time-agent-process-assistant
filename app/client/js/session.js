export class LiveSession {
  constructor(callbacks = {}) {
    this.callbacks = callbacks;
    this.socket = null;
    this.sessionId = null;
    this.userId = null;
    this.budget = null;
    this.intentionalClose = false;
    this.reconnects = 0;
    this.maxReconnects = 3;
  }

  get connected() {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  async start() {
    this.intentionalClose = false;
    this.reconnects = 0;
    const response = await fetch("/session", { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? `Could not create session (${response.status})`);
    }

    const session = await response.json();
    this.sessionId = session.session_id;
    this.userId = session.user_id;
    this.budget = session.budget;
    await this.#connect();
    return session;
  }

  sendText(text) {
    this.#send({ type: "text", text });
  }

  sendAudio(arrayBuffer) {
    this.#send({
      type: "audio",
      mimeType: "audio/pcm;rate=16000",
      data: arrayBufferToBase64(arrayBuffer),
    });
  }

  sendAudioStreamEnd() {
    this.#send({ type: "control", action: "audio_end" });
  }

  async sendImage(blob, reason = "change") {
    const arrayBuffer = await blob.arrayBuffer();
    this.#send({
      type: "image",
      mimeType: "image/jpeg",
      reason,
      data: arrayBufferToBase64(arrayBuffer),
    });
  }

  stop() {
    this.intentionalClose = true;
    if (this.connected) {
      this.#send({ type: "control", action: "close" });
    }
    this.socket?.close(1000, "Session stopped");
    this.socket = null;
  }

  async #connect() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const url = new URL(`${scheme}//${location.host}/live`);
    url.searchParams.set("session_id", this.sessionId);
    url.searchParams.set("user_id", this.userId);

    await new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      this.socket = socket;
      const connectTimeout = window.setTimeout(() => {
        socket.close();
        reject(new Error("Timed out connecting to the local Live server"));
      }, 12_000);

      socket.addEventListener(
        "open",
        () => {
          window.clearTimeout(connectTimeout);
          resolve();
        },
        { once: true },
      );
      socket.addEventListener(
        "error",
        () => {
          window.clearTimeout(connectTimeout);
          reject(new Error("Could not connect to the local Live server"));
        },
        { once: true },
      );
      socket.addEventListener("message", (event) => this.#onMessage(event));
      socket.addEventListener("close", (event) => this.#onClose(event));
    });
  }

  #onMessage(message) {
    if (typeof message.data !== "string") {
      this.callbacks.onBinaryAudio?.(message.data);
      return;
    }
    try {
      const payload = JSON.parse(message.data);
      if (payload.serverEvent) {
        this.callbacks.onServerEvent?.(payload);
      } else {
        this.callbacks.onAdkEvent?.(payload);
      }
    } catch (error) {
      this.callbacks.onError?.(new Error(`Invalid server event: ${error.message}`));
    }
  }

  async #onClose(event) {
    this.callbacks.onClose?.(event);
    if (this.intentionalClose || this.reconnects >= this.maxReconnects) {
      return;
    }

    this.reconnects += 1;
    this.callbacks.onReconnect?.(this.reconnects);
    await delay(Math.min(1000 * 2 ** (this.reconnects - 1), 5000));
    try {
      await this.#connect();
    } catch (error) {
      this.callbacks.onError?.(error);
    }
  }

  #send(payload) {
    if (!this.connected) {
      throw new Error("Live session is not connected");
    }
    this.socket.send(JSON.stringify(payload));
  }
}

function arrayBufferToBase64(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  let binary = "";
  const stride = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += stride) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + stride));
  }
  return btoa(binary);
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
