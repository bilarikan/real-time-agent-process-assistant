const FOLLOW_THRESHOLD_PX = 80;

export class TranscriptView {
  constructor({ container, template, showToolCalls = () => true }) {
    this.container = container;
    this.template = template;
    this.showToolCalls = showToolCalls;
    this.inputStream = null;
    this.outputStream = null;
    this.pendingCitations = new Set();
    this.followLatest = true;

    container.addEventListener("scroll", () => {
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      this.followLatest = distanceFromBottom <= FOLLOW_THRESHOLD_PX;
    });
    new MutationObserver(() => {
      if (this.followLatest) {
        this.#scrollToLatest();
      }
    }).observe(container, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    });
  }

  addTyped(text) {
    this.followLatest = true;
    this.#createMessage("typed", "Rep · typed", text, false);
  }

  addSystem(text) {
    this.#createMessage("tool", "System", text, false);
  }

  handleAdkEvent(event) {
    const input = event.inputTranscription;
    if (input?.text) {
      this.inputStream = this.#updateStream(
        this.inputStream,
        "call",
        "Call audio",
        input.text,
        Boolean(event.partial),
      );
      if (input.finished) {
        this.#finishStream("inputStream");
      }
    }

    const output = event.outputTranscription;
    if (output?.text) {
      this.outputStream = this.#updateStream(
        this.outputStream,
        "agent",
        "Assistant",
        output.text,
        Boolean(event.partial),
      );
      this.#applyCitations();
      if (output.finished) {
        this.#finishStream("outputStream");
      }
    }

    for (const part of event.content?.parts ?? []) {
      this.#handlePart(part);
    }

    if (event.interrupted) {
      this.markInterrupted();
    }
    if (event.turnComplete) {
      this.#finishStream("inputStream");
      this.#finishStream("outputStream");
    }
  }

  finishCallAudio() {
    this.#finishStream("inputStream");
  }

  markInterrupted() {
    if (this.outputStream?.element) {
      this.outputStream.element.dataset.interrupted = "true";
    }
    this.#finishStream("outputStream");
  }

  reset() {
    this.container.replaceChildren();
    this.inputStream = null;
    this.outputStream = null;
    this.pendingCitations.clear();
    this.followLatest = true;
  }

  #handlePart(part) {
    const call = part.functionCall;
    if (call) {
      const citation = citationFromToolCall(call);
      if (citation) {
        this.pendingCitations.add(citation);
        this.#applyCitations();
      }
      if (this.showToolCalls()) {
        this.#createMessage(
          "tool",
          "Tool",
          `Consulting ${formatToolName(call.name)}…`,
          false,
        );
      }
    }

    const response = part.functionResponse;
    if (response && this.showToolCalls()) {
      this.#createMessage(
        "tool",
        "Tool",
        `${formatToolName(response.name)} complete`,
        false,
      );
    }
  }

  #updateStream(stream, channel, author, text, partial) {
    const state =
      stream ??
      {
        element: this.#createMessage(channel, author, "", true),
        committed: "",
        pending: "",
      };

    if (partial) {
      state.pending += text;
    } else {
      if (state.committed && text.startsWith(state.committed)) {
        state.committed = text;
      } else if (text !== state.committed) {
        state.committed += text;
      }
      state.pending = "";
    }

    state.element.querySelector(".message-body").textContent =
      state.committed + state.pending;
    state.element.dataset.partial = String(partial);
    return state;
  }

  #finishStream(property) {
    const stream = this[property];
    if (!stream) {
      return;
    }
    if (!stream.committed && stream.pending) {
      stream.committed = stream.pending;
      stream.pending = "";
      stream.element.querySelector(".message-body").textContent = stream.committed;
    }
    stream.element.dataset.partial = "false";
    this[property] = null;
  }

  #createMessage(channel, author, text, partial) {
    this.container.querySelector(".empty-state")?.remove();
    const element = this.template.content.firstElementChild.cloneNode(true);
    element.dataset.channel = channel;
    element.dataset.partial = String(partial);
    element.querySelector(".message-author").textContent = author;
    element.querySelector("time").textContent = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    element.querySelector(".message-body").textContent = text;
    this.container.append(element);
    return element;
  }

  #applyCitations() {
    const element = this.outputStream?.element;
    if (!element || !this.pendingCitations.size) {
      return;
    }

    const list = element.querySelector(".citation-list");
    for (const concept of this.pendingCitations) {
      if (list.querySelector(`[data-concept="${CSS.escape(concept)}"]`)) {
        continue;
      }
      const link = document.createElement("a");
      link.className = "citation";
      link.dataset.concept = concept;
      link.href = `/knowledge${concept}.md`;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = concept;
      list.append(link);
    }
    this.pendingCitations.clear();
  }

  #scrollToLatest() {
    this.container.scrollTop = this.container.scrollHeight;
  }
}

function citationFromToolCall(call) {
  if (call.name === "okf_read") {
    const concept = call.args?.concept;
    if (typeof concept === "string") {
      return `/${concept.replace(/^\/+/, "").replace(/\.md$/, "")}`;
    }
  }
  const calculationSources = {
    compute_installment_refund: "/pricing-and-discounts/installment-refunds",
    compute_proration: "/pricing-and-discounts/proration",
    build_discount_note: "/pricing-and-discounts/discount-codes",
  };
  return calculationSources[call.name] ?? null;
}

function formatToolName(value = "") {
  return value.replaceAll("_", " ");
}
