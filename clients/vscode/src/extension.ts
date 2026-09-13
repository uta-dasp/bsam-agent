import * as path from "node:path";
import * as vscode from "vscode";
import { BsamApiError } from "./apiClient";
import { CapabilitiesTree } from "./capabilitiesTree";
import { diagnosticEntries } from "./diagnosticModel";
import { relativeWorkspacePath } from "./pathing";
import { ServerManager } from "./serverManager";
import {
  ApplyChangeResponse,
  CapabilitiesResponse,
  ChangePlanResponse,
  MeshImportResponse,
  ReviewedPlan,
  RunStatusResponse,
  ValidationResponse,
} from "./types";
import {
  defaultChangeDestination,
  defaultPlanPath,
  defaultRunDirectory,
  nonEmpty,
} from "./workflow";

let server: ServerManager | undefined;
const LAST_PLAN_KEY = "bsamAgent.lastReviewedPlan";
const LAST_RUN_KEY = "bsamAgent.lastRunDirectory";

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

function activeDeck(): vscode.TextDocument {
  const document = activeDocument();
  if (isMeshDocument(document)) {
    throw new Error("This command requires a BSAM deck, not an .ele mesh");
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

async function showDiff(plan: ChangePlanResponse): Promise<void> {
  const document = await vscode.workspace.openTextDocument({
    content: plan.source_diff,
    language: "diff",
  });
  await vscode.window.showTextDocument(document, { preview: true });
  void vscode.window.setStatusBarMessage(`BSAM Agent: reviewed plan ${plan.plan_id}`, 5000);
}

function workspaceArgument(workspaceRoot: string, value: string): string {
  const absolute = path.isAbsolute(value) ? value : path.resolve(workspaceRoot, value);
  return relativeWorkspacePath(workspaceRoot, absolute);
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

  const validate = async (document: vscode.TextDocument, startIfNeeded: boolean): Promise<number> => {
    const manager = server;
    if (!manager) {
      return 0;
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
      return 0;
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
    return result.summary.errors;
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
    vscode.commands.registerCommand("bsamAgent.previewParameterChange", async () => {
      try {
        const document = activeDeck();
        const manager = server!;
        const workspaceRoot = manager.workspaceRoot();
        const source = relativeWorkspacePath(workspaceRoot, document.uri.fsPath);
        const block = nonEmpty(await vscode.window.showInputBox({
          title: "BSAM block",
          prompt: "Top-level block containing the construct (for example BOUNDARY)",
          ignoreFocusOut: true,
        }));
        if (!block) return;
        const construct = nonEmpty(await vscode.window.showInputBox({
          title: "BSAM construct",
          prompt: "Registered construct to edit (for example CONVERGENCE)",
          ignoreFocusOut: true,
        }));
        if (!construct) return;
        const parameter = nonEmpty(await vscode.window.showInputBox({
          title: "BSAM parameter",
          prompt: "Registered parameter name",
          ignoreFocusOut: true,
        }));
        if (!parameter) return;
        const value = nonEmpty(await vscode.window.showInputBox({
          title: "New value",
          prompt: "Exact BSAM value; the deterministic core validates its schema",
          ignoreFocusOut: true,
        }));
        if (value === undefined) return;
        const occurrenceText = nonEmpty(await vscode.window.showInputBox({
          title: "Construct occurrence",
          prompt: "One-based occurrence",
          value: "1",
          validateInput: (candidate) => /^[1-9]\d*$/.test(candidate.trim())
            ? undefined : "Enter a positive integer",
          ignoreFocusOut: true,
        }));
        if (!occurrenceText) return;
        const planPath = defaultPlanPath(source);
        await vscode.workspace.fs.createDirectory(vscode.Uri.file(path.join(workspaceRoot, path.dirname(planPath))));
        const { client } = await manager.ensureStarted();
        const plan = await client.invoke<ChangePlanResponse>("preview_parameter_change", {
          source,
          block,
          construct,
          parameter,
          value,
          occurrence: Number(occurrenceText),
          plan_path: planPath,
        });
        const reviewed: ReviewedPlan = {
          source,
          planPath,
          planId: plan.plan_id,
          planDigest: plan.plan_digest,
        };
        await context.workspaceState.update(LAST_PLAN_KEY, reviewed);
        await showDiff(plan);
        status.text = `$(diff) BSAM plan ${plan.plan_id} reviewed`;
        output.appendLine(`Reviewed plan ${plan.plan_id} (${plan.plan_digest}) at ${planPath}.`);
        void vscode.window.showInformationMessage(
          `BSAM change plan ${plan.plan_id} is ready. Review the displayed diff before applying it.`,
        );
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.applyReviewedChange", async () => {
      try {
        const reviewed = context.workspaceState.get<ReviewedPlan>(LAST_PLAN_KEY);
        if (!reviewed) {
          throw new Error("No reviewed change plan is available in this workspace");
        }
        const manager = server!;
        const { client } = await manager.ensureStarted();
        const current = await client.invoke<ChangePlanResponse>("review_change", {
          plan_path: reviewed.planPath,
        });
        if (current.plan_id !== reviewed.planId || current.plan_digest !== reviewed.planDigest) {
          throw new Error("The reviewed plan identity changed; create and review a new plan");
        }
        await showDiff(current);
        const destination = nonEmpty(await vscode.window.showInputBox({
          title: "New deck destination",
          prompt: "Workspace-relative output path; existing files are never overwritten",
          value: defaultChangeDestination(reviewed.source),
          ignoreFocusOut: true,
        }));
        if (!destination) return;
        const confirmation = `Apply plan ${reviewed.planId}`;
        const selected = await vscode.window.showWarningMessage(
          `Apply reviewed plan ${reviewed.planId} to ${destination}?`,
          { modal: true, detail: `Plan digest: ${reviewed.planDigest}` },
          confirmation,
        );
        if (selected !== confirmation) return;
        status.text = "$(sync~spin) BSAM applying change";
        const result = await client.invoke<ApplyChangeResponse>("apply_change", {
          plan_path: reviewed.planPath,
          destination,
          confirm: true,
        });
        status.text = `$(check) BSAM applied ${result.plan_id}`;
        output.appendLine(`Applied plan ${result.plan_id} to ${result.destination}; audit ${result.audit}.`);
        void vscode.window.showInformationMessage(`BSAM change written to ${result.destination}.`);
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.runCurrentFile", async () => {
      try {
        const document = activeDeck();
        if (await validate(document, true)) {
          throw new Error("Run blocked because the current model has validation errors");
        }
        const manager = server!;
        const workspaceRoot = manager.workspaceRoot();
        const source = relativeWorkspacePath(workspaceRoot, document.uri.fsPath);
        const configured = vscode.workspace.getConfiguration("bsamAgent").get<string>("executablePath", "").trim();
        let executable = configured ? workspaceArgument(workspaceRoot, configured) : undefined;
        if (!executable) {
          const selected = await vscode.window.showOpenDialog({
            title: "Select the workspace-local BSAM executable",
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: false,
            defaultUri: vscode.Uri.file(workspaceRoot),
            filters: { Executable: ["exe"] },
          });
          if (!selected?.length) return;
          executable = relativeWorkspacePath(workspaceRoot, selected[0].fsPath);
        }
        const outputDir = defaultRunDirectory(source);
        const timeout = vscode.workspace.getConfiguration("bsamAgent").get<number>("runTimeoutSeconds", 3600);
        const stopGrace = vscode.workspace.getConfiguration("bsamAgent").get<number>("stopGraceSeconds", 30);
        const confirmation = "Start verified BSAM run";
        const selected = await vscode.window.showWarningMessage(
          `Run ${source} with ${executable}?`,
          { modal: true, detail: `Output: ${outputDir}\nTimeout: ${timeout} seconds` },
          confirmation,
        );
        if (selected !== confirmation) return;
        const { client } = await manager.ensureStarted();
        const result = await client.invoke<RunStatusResponse>("run_bsam", {
          source,
          output_dir: outputDir,
          executable,
          timeout,
          stop_grace: stopGrace,
          confirm: true,
        });
        await context.workspaceState.update(LAST_RUN_KEY, outputDir);
        status.text = "$(run) BSAM run accepted";
        output.appendLine(`Run accepted in ${result.output_directory}.`);
        void vscode.window.showInformationMessage(`BSAM run accepted: ${outputDir}`);
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.showRunStatus", async () => {
      try {
        const outputDir = context.workspaceState.get<string>(LAST_RUN_KEY);
        if (!outputDir) throw new Error("No BSAM run has been started from this workspace");
        const { client } = await server!.ensureStarted();
        const result = await client.invoke<RunStatusResponse>("get_run_status", { output_dir: outputDir });
        status.text = result.state === "terminal"
          ? `$(check) BSAM ${result.classification}`
          : `$(run) BSAM ${result.state}`;
        await showJson(result, `run ${result.classification}`);
      } catch (error) {
        report(error, output);
      }
    }),
    vscode.commands.registerCommand("bsamAgent.stopRun", async () => {
      try {
        const outputDir = context.workspaceState.get<string>(LAST_RUN_KEY);
        if (!outputDir) throw new Error("No BSAM run has been started from this workspace");
        const confirmation = "Request controlled stop";
        const selected = await vscode.window.showWarningMessage(
          `Request a controlled stop for ${outputDir}?`,
          { modal: true },
          confirmation,
        );
        if (selected !== confirmation) return;
        const { client } = await server!.ensureStarted();
        const result = await client.invoke<RunStatusResponse>("stop_run", {
          output_dir: outputDir,
          confirm: true,
        });
        status.text = "$(stop) BSAM stop requested";
        output.appendLine(`Controlled stop requested for ${result.output_directory}.`);
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
