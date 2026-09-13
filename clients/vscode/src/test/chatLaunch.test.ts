import assert from "node:assert/strict";
import test from "node:test";
import { chatArguments } from "../chatLaunch";

test("builds an audited persistent local chat launch", () => {
  assert.deepEqual(chatArguments("D:\\work", "config/provider.local.json", ".bsam-agent/chat.json", true), [
    "-m", "bsam_agent", "chat",
    "--workspace-root", "D:\\work",
    "--config", "config/provider.local.json",
    "--session", ".bsam-agent/chat.json",
  ]);
});

test("can explicitly disable digest audit metadata", () => {
  assert.equal(chatArguments("root", "config", "session", false).at(-1), "--no-audit");
});
