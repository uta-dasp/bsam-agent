import * as path from "node:path";
import { existsSync } from "node:fs";

function comparable(value: string): string {
  const resolved = path.resolve(value).replace(/[\\/]+$/, "");
  return process.platform === "win32" ? resolved.toLocaleLowerCase("en-US") : resolved;
}

export function sameWorkspaceRoot(first: string, second: string): boolean {
  return comparable(first) === comparable(second);
}

export function relativeWorkspacePath(workspaceRoot: string, filePath: string): string {
  const relative = path.relative(path.resolve(workspaceRoot), path.resolve(filePath));
  if (!relative || relative === ".") {
    throw new Error("A model file, not the workspace root, must be selected");
  }
  if (path.isAbsolute(relative) || relative === ".." || relative.startsWith(`..${path.sep}`)) {
    throw new Error("The selected file is outside the BSAM Agent workspace root");
  }
  return relative.replaceAll(path.sep, "/");
}

export function resolveDiagnosticSource(
  workspaceRoot: string,
  rootFilePath: string,
  source: string | undefined,
): string {
  if (!source || source === "<root>") {
    return path.resolve(rootFilePath);
  }
  if (path.isAbsolute(source)) {
    const relative = relativeWorkspacePath(workspaceRoot, source);
    return path.resolve(workspaceRoot, relative);
  }
  return path.resolve(workspaceRoot, source);
}

export function resolveRepositoryRoot(
  workspaceRoot: string,
  extensionPath: string,
  configured: string,
  exists: (candidate: string) => boolean = existsSync,
): string {
  if (configured.trim() && !path.isAbsolute(configured.trim())) {
    throw new Error("bsamAgent.repositoryRoot must be an absolute path");
  }
  const candidates = configured.trim()
    ? [path.resolve(configured.trim())]
    : [
      path.resolve(workspaceRoot),
      path.resolve(workspaceRoot, "bsam agent"),
      path.resolve(extensionPath, "..", ".."),
    ];
  const selected = candidates.find((candidate) => exists(path.join(candidate, "src", "bsam_agent")));
  if (!selected) {
    throw new Error("Cannot locate the BSAM Agent repository; configure bsamAgent.repositoryRoot");
  }
  return selected;
}
