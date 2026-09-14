import assert from "node:assert/strict";
import test from "node:test";
import { chatArguments } from "../chatLaunch";

test("builds an audited persistent local chat launch", () => {
  assert.deepEqual(chatArguments("D:\\work", "config/provider.local.json", ".bsam-agent/chat.json", true), [
    "-m", "bsam_agent", "chat",
    "--workspace-root", "D:\\work",
    "--config", "config/provider.local.json",
    "--session", ".bsam-agent/chat.json",
    "--jsonl",
  ]);
});

test("can explicitly disable digest audit metadata", () => {
  assert.equal(chatArguments("root", "config", "session", false).at(-1), "--no-audit");
});

test("passes provider model and reasoning selections without a credential", () => {
  assert.deepEqual(
    chatArguments("root", "config", "session", true, "openai", "gpt-5.6-terra", "high").slice(-6),
    ["--provider", "openai", "--model", "gpt-5.6-terra", "--reasoning-effort", "high"],
  );
});
