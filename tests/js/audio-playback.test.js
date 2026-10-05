import assert from "node:assert/strict";
import test from "node:test";

import { base64ToBytes } from "../../app/client/js/audio-playback.js";

test("decodes ADK's URL-safe Base64 audio payloads", () => {
  assert.deepEqual([...base64ToBytes("-__-")], [251, 255, 254]);
});

test("continues to decode standard padded Base64", () => {
  assert.deepEqual([...base64ToBytes("+//+")], [251, 255, 254]);
});
