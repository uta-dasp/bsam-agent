import assert from "node:assert/strict";
import test from "node:test";
import { editableCapabilities } from "../formModel";
import { CapabilitiesResponse, QueryCapabilityRecord } from "../types";

const capabilities = {
  capabilities: {
    operational_manifest: [
      {
        id: "construct.boundary-convergence",
        kind: "nested-construct",
        canonical: "*CONVERGENCE",
        parent: "BOUNDARY",
        specification_maturity: "documented",
        operations: { modify: "verified" },
        intents: {},
        parameter_edits: [{
          name: "maxiterations",
          cardinality: "repeated-last-wins",
          operations: { insert: "verified", remove: "verified" },
        }],
      },
    ],
  },
} as unknown as CapabilitiesResponse;

test("derives editable forms from registry support and root semantic occurrences", () => {
  const records: QueryCapabilityRecord[] = [{
    id: "construct.boundary-convergence[1]@<root>:23",
    capability_id: "construct.boundary-convergence",
    canonical: "*CONVERGENCE",
    occurrence: 1,
    location: { source: "<root>", line: 23 },
    parameters: { absolute: [{ value: "1" }] },
    defaults: { absolute: 100000000, maxiterations: 20, not_insertable: 0 },
    operations: { modify: "verified" },
  }];
  assert.deepEqual(editableCapabilities(records, capabilities), [{
    capabilityId: "construct.boundary-convergence",
    block: "BOUNDARY",
    construct: "*CONVERGENCE",
    occurrence: 1,
    line: 23,
    parameters: [
      { name: "absolute", currentValues: ["1"], defaultValue: "100000000", appendVerified: false },
      { name: "maxiterations", currentValues: [], defaultValue: "20", appendVerified: true },
    ],
  }]);
});

test("excludes included occurrences because parameter plans target the root deck", () => {
  const records: QueryCapabilityRecord[] = [{
    id: "included",
    capability_id: "construct.boundary-convergence",
    canonical: "*CONVERGENCE",
    occurrence: 1,
    location: { source: "mesh/include.in", line: 2 },
    parameters: { absolute: [{ value: "1" }] },
    defaults: {},
    operations: { modify: "verified" },
  }];
  assert.deepEqual(editableCapabilities(records, capabilities), []);
});
