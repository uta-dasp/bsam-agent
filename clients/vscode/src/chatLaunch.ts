export function chatArguments(
  workspaceRoot: string,
  configPath: string,
  sessionPath: string,
  auditEnabled: boolean,
  provider?: string,
  model?: string,
  reasoningEffort?: string,
): string[] {
  const result = [
    "-m",
    "bsam_agent",
    "chat",
    "--workspace-root",
    workspaceRoot,
    "--config",
    configPath,
    "--session",
    sessionPath,
    "--jsonl",
  ];
  if (provider && provider !== "configured") result.push("--provider", provider);
  if (model) result.push("--model", model);
  if (reasoningEffort) result.push("--reasoning-effort", reasoningEffort);
  if (!auditEnabled) result.push("--no-audit");
  return result;
}
