import * as path from "node:path";
import * as vscode from "vscode";
import { BsamApiError } from "./apiClient";
import { CapabilitiesTree } from "./capabilitiesTree";
import { diagnosticEntries } from "./diagnosticModel";
import { relativeWorkspacePath } from "./pathing";
import { ServerManager } from "./serverManager";
import { CapabilitiesResponse, MeshImportResponse, ValidationResponse } from "./types";

let server: ServerManager | undefined;

function supportedDocument(document: vscode.TextDocument): boolean {
  return [".in", ".bsam", ".ele"].includes(path.extname(document.uri.fsPath).toLocaleLowerCase("en-US"));
}

function isMeshDocument(document: vscode.TextDocument): boolean {
  return path.extname(document.uri.fsPath).toLocaleLowerCase("en-US") === ".ele";
}

function activeDocument(): vscode.TextDocument {
  const document = vscode.window.activeTextEditor?.document;
  if (!document || document.uri.scheme !== "file" || !supportedDocument(document)) {
    throw new Error("Open a workspace-local .in, .bsam, or .ele file first");
  }
  return document;
}

function report(error: unknown, output: vscode.OutputChannel): void {
  const message = error instanceof BsamApiError
    ? `${error.code}: ${error.message}`
    : error instanceof Error ? error.message : String(error);
  output.appendLine(`ERROR ${message}`);
  void vscode.window.showErrorMessage(`BSAM Agent: ${message}`);
}

async function showJson(value: unknown, title: string): Promise<void> {
  const document = await vscode.workspace.openTextDocument({
    content: JSON.stringify(value, null, 2),
    language: "json",
  });
  await vscode.window.showTextDocument(document, { preview: true });
  void vscode.window.setStatusBarMessage(`BSAM Agent: ${title}`, 5000);
}

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("BSAM Agent", { log: true });
  const diagnostics = vscode.languages.createDiagnosticCollection("bsam-agent");
  server = new ServerManager(context, output);
  const capabilitiesTree = new CapabilitiesTree(server);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  status.name = "BSAM Agent";
  status.command = "bsamAgent.openOutput";
  status.text = "$(beaker) BSAM Agent";
  status.tooltip = "Open BSAM Agent output";
  status.show();

  const validate = async (document: vscode.TextDocument, startIfNeeded: boolean): Promise<void> => {
    const manager = server;
    if (!manager) {
      return;
    }
    const workspaceRoot = manager.workspaceRoot();
    const source = relativeWorkspacePath(workspaceRoot, document.uri.fsPath);
    const connection = startIfNeeded ? await manager.ensureStarted() : await manager.connect();
    status.text = "$(sync~spin) BSAM validating";
    if (isMeshDocument(document)) {
      const result = await connection.client.invoke<MeshImportResponse>("import_mesh", { source });
      diagnostics.delete(document.uri);
      status.text = `$(check) BSAM mesh: ${result.summary.nodes} nodes, ${result.summary.elements} elements`;
      output.appendLine(
        `Validated mesh ${source}: ${result.summary.nodes} node(s), ${result.summary.elements} element(s).`,
      );
      return;
    }
    const result = await connection.client.invoke<ValidationResponse>("validate_model", { source });
    diagnostics.clear();
    const grouped = new Map<string, vscode.Diagnostic[]>();
    for (const entry of diagnosticEntries(workspaceRoot, document.uri.fsPath, result.diagnostics)) {
      const severity = entry.severity === "error"
        ? vscode.DiagnosticSeverity.Error
        : entry.severity === "warning"
          ? vscode.DiagnosticSeverity.Warning
          : vscode.DiagnosticSeverity.Information;
      const diagnostic = new vscode.Diagnostic(
        new vscode.Range(entry.line, entry.column, entry.endLine, entry.endColumn),
        entry.message,
        severity,
      );
      diagnostic.code = entry.code;
      diagnostic.source = entry.detail ? `BSAM Agent · ${entry.detail}` : "BSAM Agent";
      const values = grouped.get(entry.filePath) ?? [];
      values.push(diagnostic);
      grouped.set(entry.filePath, values);
    }
    for (const [filePath, values] of grouped) {
      diagnostics.set(vscode.Uri.file(filePath), values);
    }
    status.text = result.summary.errors
      ? `$(error) BSAM ${result.summary.errors} error(s)`
      : `$(check) BSAM valid${result.summary.warnings ? ` · ${result.summary.warnings} warning(s)` : ""}`;
    output.appendLine(
      `Validated ${source}: ${result.summary.errors} error(s), ${result.summary.warnings} warning(s).`,
    );
  };

  context.subscriptions.push(
    output,
    diagnostics,
    server,
    status,
    vscode.window.registerTreeDataProvider("bsamAgent.capabilities", capabilitiesTree),
    vscode.commands.registerCommand("bsamAgent.startServer", async () => {
      try {
        await server?.start();
        status.text = "$(check) BSAM API ready";
        await capabilitiesTree.refresh();
        void vscode.window.showInformationMessage("BSAM Agent API is ready.");
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.stopServer", async () => {
      try {
        const stopped = await server?.stop();
        status.text = "$(beaker) BSAM Agent";
        void vscode.window.showInformationMessage(
          stopped ? "Stopped the extension-owned BSAM Agent API." : "No extension-owned API is running.",
        );
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.validateCurrentFile", async () => {
      try {
        await validate(activeDocument(), true);
      } catch (error) {
        status.text = "$(error) BSAM unavailable";
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.inspectCurrentFile", async () => {
      try {
        const document = activeDocument();
        const manager = server!;
        const source = relativeWorkspacePath(manager.workspaceRoot(), document.uri.fsPath);
        const { client } = await manager.ensureStarted();
        const tool = isMeshDocument(document) ? "import_mesh" : "inspect_model";
        const result = await client.invoke<Record<string, unknown>>(tool, { source });
        await showJson(result, `inspected ${source}`);
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.refreshCapabilities", async () => {
      try {
        await capabilitiesTree.refresh();
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.showCapabilitiesJson", async () => {
      try {
        const { client } = await server!.ensureStarted();
        await showJson(await client.capabilities() as CapabilitiesResponse, "capabilities loaded");
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.openOutput", () => output.show(true)),
    vscode.workspace.onDidSaveTextDocument(async (document) => {
      if (!supportedDocument(document)
          || !vscode.workspace.getConfiguration("bsamAgent").get<boolean>("validation.onSave", true)) {
        return;
      }
      try {
        await validate(document, false);
      } catch (error) {
        if (!(error instanceof BsamApiError) || error.code !== "unavailable") {
          report(error, output);
        }
      }
    }),
  );
}

export function deactivate(): void {
  server?.dispose();
  server = undefined;
}
