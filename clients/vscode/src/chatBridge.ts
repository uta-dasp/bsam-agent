import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";

export interface ChatBridgeOptions {
  executable: string;
  arguments: string[];
  cwd: string;
  env: NodeJS.ProcessEnv;
}

export type ChatProtocolMessage = Record<string, unknown> & { type: string };

export class JsonLineDecoder {
  private buffer = "";

  push(chunk: string): string[] {
    this.buffer += chunk;
    const lines = this.buffer.split(/\r?\n/);
    this.buffer = lines.pop() ?? "";
    return lines.filter((line) => line.length > 0);
  }
}

export class ChatBridge {
  private readonly process: ChildProcessWithoutNullStreams;
  private readonly decoder = new JsonLineDecoder();

  constructor(
    options: ChatBridgeOptions,
    onMessage: (message: ChatProtocolMessage) => void,
    onError: (message: string) => void,
    onExit: (code: number | null, signal: NodeJS.Signals | null) => void,
  ) {
    this.process = spawn(options.executable, options.arguments, {
      cwd: options.cwd,
      env: options.env,
      windowsHide: true,
    });
    this.process.stdout.on("data", (data: Buffer) => {
      for (const line of this.decoder.push(data.toString("utf-8"))) {
        try {
          const value = JSON.parse(line) as unknown;
          if (!value || typeof value !== "object" || typeof (value as { type?: unknown }).type !== "string") {
            throw new Error("chat message is not an object with a type");
          }
          onMessage(value as ChatProtocolMessage);
        } catch (error) {
          onError(`Invalid local chat response: ${error instanceof Error ? error.message : String(error)}`);
        }
      }
    });
    this.process.stderr.on("data", (data: Buffer) => onError(data.toString("utf-8").trim()));
    this.process.on("error", (error) => onError(`Unable to start local chat: ${error.message}`));
    this.process.on("exit", onExit);
  }

  send(text: string): void {
    if (this.process.exitCode !== null || !this.process.stdin.writable) {
      throw new Error("The local chat process is not running");
    }
    this.process.stdin.write(JSON.stringify({ type: "turn", text }) + "\n");
  }

  dispose(): void {
    if (this.process.exitCode === null) {
      this.process.kill();
    }
  }
}
