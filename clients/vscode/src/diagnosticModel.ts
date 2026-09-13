import { resolveDiagnosticSource } from "./pathing";
import { ValidationDiagnostic } from "./types";

export interface DiagnosticEntry {
  filePath: string;
  line: number;
  column: number;
  endLine: number;
  endColumn: number;
  severity: "error" | "warning" | "information";
  code: string;
  message: string;
  detail: string;
}

export function diagnosticEntries(
  workspaceRoot: string,
  rootFilePath: string,
  diagnostics: ValidationDiagnostic[],
): DiagnosticEntry[] {
  return diagnostics.map((item) => {
    const location = item.location ?? {};
    const line = Math.max(0, (location.line ?? 1) - 1);
    const column = Math.max(0, (location.column ?? 1) - 1);
    const endLine = Math.max(line, (location.line_end ?? location.line ?? 1) - 1);
    const endColumn = Math.max(column + 1, location.column_end ?? column + 1);
    const severity = item.severity === "error"
      ? "error"
      : item.severity === "warning"
        ? "warning"
        : "information";
    return {
      filePath: resolveDiagnosticSource(workspaceRoot, rootFilePath, location.source),
      line,
      column,
      endLine,
      endColumn,
      severity,
      code: item.code ?? "BSAM",
      message: item.message ?? "BSAM validation diagnostic",
      detail: [item.level, item.provenance].filter(Boolean).join(" · "),
    };
  });
}
