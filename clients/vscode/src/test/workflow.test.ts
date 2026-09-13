import assert from "node:assert/strict";
import test from "node:test";
import {
  defaultChangeDestination,
  defaultPlanPath,
  defaultRunDirectory,
  nonEmpty,
  timestampToken,
} from "../workflow";

const instant = new Date("2026-09-13T12:34:56.789Z");

test("creates collision-resistant workspace artifact paths", () => {
  assert.equal(timestampToken(instant), "20260913T123456-789Z");
  assert.equal(
    defaultPlanPath("models/notch v1.in", instant),
    ".bsam-agent/plans/notch-v1-20260913T123456-789Z.json",
  );
  assert.equal(
    defaultChangeDestination("models/notch v1.in", instant),
    ".bsam-agent/changes/notch-v1-20260913T123456-789Z/notch v1.in",
  );
  assert.equal(
    defaultRunDirectory("models/notch v1.in", instant),
    ".bsam-agent/runs/notch-v1-20260913T123456-789Z",
  );
});

test("normalizes optional form input", () => {
  assert.equal(nonEmpty("  value  "), "value");
  assert.equal(nonEmpty("   "), undefined);
  assert.equal(nonEmpty(undefined), undefined);
});
