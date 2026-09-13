import * as path from "node:path";

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
