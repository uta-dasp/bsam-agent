import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import * as path from "node:path";
import * as vscode from "vscode";
import { BsamApiClient, BsamApiError } from "./apiClient";
import { sameWorkspaceRoot } from "./pathing";
import { HealthResponse } from "./types";

export class ServerManager implements vscode.Disposable {
  private process: ChildProcessWithoutNullStreams | undefined;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly output: vscode.OutputChannel,
  ) {}

  workspaceRoot(): string {
    const configured = vscode.workspace.getConfiguration("bsamAgent").get<string>("workspaceRoot", "").trim();
    if (configured) {
      if (!path.isAbsolute(configured)) {
        throw new Error("bsamAgent.workspaceRoot must be an absolute path");
      }
      return path.resolve(configured);
    }
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      throw new Error("Open a workspace folder or configure bsamAgent.workspaceRoot");
    }
    return folder.uri.fsPath;
  }

  client(): BsamApiClient {
    const configuration = vscode.workspace.getConfiguration("bsamAgent");
    return new BsamApiClient(
      configuration.get<number>("apiPort", 8765),
      configuration.get<number>("requestTimeoutMs", 120000),
    );
  }

  async connect(): Promise<{ client: BsamApiClient; health: HealthResponse }> {
    const client = this.client();
    const health = await client.health();
    this.assertWorkspace(health);
    return { client, health };
  }

  async ensureStarted(): Promise<{ client: BsamApiClient; health: HealthResponse }> {
    try {
      return await this.connect();
    } catch (error) {
      if (!(error instanceof BsamApiError) || error.code !== "unavailable") {
        throw error;
      }
    }
    await this.start();
    return this.connect();
  }

  async start(): Promise<void> {
    try {
      await this.connect();
      this.output.appendLine("Using the existing BSAM Agent API.");
      return;
    } catch (error) {
      if (!(error instanceof BsamApiError) || error.code !== "unavailable") {
        throw error;
      }
    }
    if (this.process && this.process.exitCode === null) {
      await this.waitUntilReady();
      return;
    }

    const configuration = vscode.workspace.getConfiguration("bsamAgent");
    const python = configuration.get<string>("pythonPath", "python");
    const port = configuration.get<number>("apiPort", 8765);
    const workspaceRoot = this.workspaceRoot();
    const repositoryRoot = path.resolve(this.context.extensionPath, "..", "..");
    const sourceRoot = path.join(repositoryRoot, "src");
    const delimiter = process.platform === "win32" ? ";" : ":";
    const pythonPath = [sourceRoot, process.env.PYTHONPATH].filter(Boolean).join(delimiter);

    this.output.appendLine(`Starting BSAM Agent API for ${workspaceRoot}`);
    this.process = spawn(
      python,
      ["-m", "bsam_agent", "serve", "--workspace-root", workspaceRoot, "--port", String(port)],
      {
        cwd: repositoryRoot,
        env: { ...process.env, PYTHONPATH: pythonPath },
        windowsHide: true,
      },
    );
    this.process.stdout.on("data", (data: Buffer) => this.output.append(data.toString()));
    this.process.stderr.on("data", (data: Buffer) => this.output.append(data.toString()));
    this.process.on("exit", (code, signal) => {
      this.output.appendLine(`BSAM Agent API exited (code=${code}, signal=${signal}).`);
      this.process = undefined;
    });
    await this.waitUntilReady();
  }

  async stop(): Promise<boolean> {
    if (!this.process || this.process.exitCode !== null) {
      return false;
    }
    const owned = this.process;
    owned.kill();
    await new Promise<void>((resolve) => {
      if (owned.exitCode !== null) {
        resolve();
        return;
      }
      const timer = setTimeout(resolve, 3000);
      owned.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
    return true;
  }

  dispose(): void {
    if (this.process && this.process.exitCode === null) {
      this.process.kill();
    }
  }

  private assertWorkspace(health: HealthResponse): void {
    const expected = this.workspaceRoot();
    if (!sameWorkspaceRoot(expected, health.workspace_root)) {
      throw new Error(
        `Port is serving a different workspace: expected ${expected}, found ${health.workspace_root}`,
      );
    }
  }

  private async waitUntilReady(): Promise<void> {
    const timeoutMs = vscode.workspace.getConfiguration("bsamAgent")
      .get<number>("serverStartupTimeoutMs", 15000);
    const deadline = Date.now() + timeoutMs;
    let lastError: unknown;
    while (Date.now() < deadline) {
      if (this.process?.exitCode !== null) {
        throw new Error(`BSAM Agent API exited before becoming ready: ${this.process?.exitCode}`);
      }
      try {
        await this.connect();
        return;
      } catch (error) {
        lastError = error;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const detail = lastError instanceof Error ? `: ${lastError.message}` : "";
    throw new Error(`BSAM Agent API did not become ready within ${timeoutMs} ms${detail}`);
  }
}
