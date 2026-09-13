import assert from "node:assert/strict";
import * as path from "node:path";
import test from "node:test";
import { diagnosticEntries } from "../diagnosticModel";

test("converts classified BSAM diagnostics to editor coordinates", () => {
  const root = path.resolve("workspace");
  const model = path.join(root, "case.in");
  const entries = diagnosticEntries(root, model, [{
    code: "BSAM-E100",
    severity: "error",
    message: "bad record",
    level: "syntax",
    provenance: "source-defined",
    location: { source: "<root>", line: 3, column: 2 },
  }]);
  assert.deepEqual(entries, [{
    filePath: model,
    line: 2,
    column: 1,
    endLine: 2,
    endColumn: 2,
    severity: "error",
    code: "BSAM-E100",
    message: "bad record",
    detail: "syntax · source-defined",
  }]);
});
