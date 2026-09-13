export function chatArguments(
  workspaceRoot: string,
  configPath: string,
  sessionPath: string,
  auditEnabled: boolean,
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
  ];
  if (!auditEnabled) result.push("--no-audit");
  return result;
}
