import assert from "node:assert/strict";
import test from "node:test";
import { JsonLineDecoder } from "../chatBridge";

test("decodes fragmented newline-delimited JSON without losing data", () => {
  const decoder = new JsonLineDecoder();
  assert.deepEqual(decoder.push('{"type":"rea'), []);
  assert.deepEqual(decoder.push('dy"}\n{"type":"turn"}\r\npartial'), [
    '{"type":"ready"}',
    '{"type":"turn"}',
  ]);
  assert.deepEqual(decoder.push("-line\n"), ["partial-line"]);
});
