import { randomBytes } from "node:crypto";
import * as path from "node:path";
import * as vscode from "vscode";
import { ChatBridge, ChatProtocolMessage } from "./chatBridge";
import { chatArguments } from "./chatLaunch";
import { relativeWorkspacePath } from "./pathing";
import { ServerManager } from "./serverManager";

export class ChatPanel implements vscode.Disposable {
  private static current: ChatPanel | undefined;
  private readonly bridge: ChatBridge;
  private readonly subscriptions: vscode.Disposable[] = [];
  private busy = true;
  private disposed = false;

  static async open(manager: ServerManager, output: vscode.OutputChannel): Promise<void> {
    if (ChatPanel.current) {
      ChatPanel.current.panel.reveal(vscode.ViewColumn.Beside, true);
      return;
    }
    const configuration = vscode.workspace.getConfiguration("bsamAgent");
    const workspaceRoot = manager.workspaceRoot();
    const sessionSetting = configuration.get<string>(
      "chat.sessionPath", ".bsam-agent/conversations/vscode.json",
    ).trim();
    if (!sessionSetting || path.isAbsolute(sessionSetting)) {
      throw new Error("bsamAgent.chat.sessionPath must be a non-empty workspace-relative path");
    }
    const sessionPath = relativeWorkspacePath(
      workspaceRoot, path.resolve(workspaceRoot, sessionSetting),
    );
    const configPath = configuration.get<string>(
      "chat.providerConfigPath", "config/provider.local.json",
    ).trim();
    if (!configPath) throw new Error("bsamAgent.chat.providerConfigPath cannot be empty");
    const provider = configuration.get<string>("provider", "configured").trim();
    const model = configuration.get<string>("model", "").trim();
    const reasoningEffort = configuration.get<string>("reasoningEffort", "").trim();
    const credentialEnvironment = provider === "openai" ? "OPENAI_API_KEY" : configuration.get<string>(
      "chat.credentialEnvironment", "BSAM_LOCAL_API_KEY",
    ).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(credentialEnvironment)) {
      throw new Error("bsamAgent.chat.credentialEnvironment is not a valid environment variable name");
    }
    const environment = manager.pythonEnvironment();
    if (!environment[credentialEnvironment]) {
      const credential = await vscode.window.showInputBox({
        title: provider === "openai" ? "OpenAI API key" : "Local model session credential",
        prompt: `Enter ${credentialEnvironment}; it is passed only to the local chat process and is not stored`,
        password: true,
        ignoreFocusOut: true,
      });
      if (!credential) return;
      environment[credentialEnvironment] = credential;
    }

    const panel = vscode.window.createWebviewPanel(
      "bsamAgent.chat",
      "BSAM Agent Chat",
      { viewColumn: vscode.ViewColumn.Beside, preserveFocus: false },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [],
      },
    );
    ChatPanel.current = new ChatPanel(
      panel,
      {
        executable: manager.pythonExecutable(),
        arguments: chatArguments(
          workspaceRoot,
          configPath,
          sessionPath,
          configuration.get<boolean>("chat.auditEnabled", true),
          provider,
          model,
          reasoningEffort,
        ),
        cwd: manager.repositoryRoot(),
        env: environment,
      },
      output,
    );
  }

  static close(): void {
    ChatPanel.current?.panel.dispose();
  }

  private constructor(
    private readonly panel: vscode.WebviewPanel,
    launch: ConstructorParameters<typeof ChatBridge>[0],
    private readonly output: vscode.OutputChannel,
  ) {
    panel.webview.html = this.html(panel.webview);
    this.subscriptions.push(
      panel.webview.onDidReceiveMessage((message: unknown) => this.receive(message)),
      panel.onDidDispose(() => this.dispose()),
    );
    this.bridge = new ChatBridge(
      launch,
      (message) => this.protocolMessage(message),
      (message) => this.bridgeError(message),
      (code, signal) => {
        this.busy = false;
        void this.panel.webview.postMessage({
          type: "closed",
          message: `Local chat process exited (code=${code}, signal=${signal}).`,
        });
      },
    );
    output.appendLine("Opened the BSAM Agent chat window.");
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    ChatPanel.current = undefined;
    this.bridge.dispose();
    while (this.subscriptions.length) this.subscriptions.pop()?.dispose();
  }

  private receive(message: unknown): void {
    if (!message || typeof message !== "object") return;
    const value = message as { command?: unknown; text?: unknown };
    if (value.command !== "send" || typeof value.text !== "string") return;
    const text = value.text.trim();
    if (!text || this.busy) return;
    try {
      this.busy = true;
      void this.panel.webview.postMessage({ type: "busy", busy: true });
      this.bridge.send(text);
    } catch (error) {
      this.busy = false;
      this.bridgeError(error instanceof Error ? error.message : String(error));
    }
  }

  private protocolMessage(message: ChatProtocolMessage): void {
    if (message.type === "ready" || message.type === "turn" || message.type === "error") {
      this.busy = false;
    }
    void this.panel.webview.postMessage(message);
  }

  private bridgeError(message: string): void {
    if (!message) return;
    this.busy = false;
    this.output.appendLine(`Local chat: ${message}`);
    void this.panel.webview.postMessage({ type: "error", message });
  }

  private html(webview: vscode.Webview): string {
    const nonce = randomBytes(16).toString("base64");
    const csp = [
      "default-src 'none'",
      `style-src 'nonce-${nonce}'`,
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>BSAM Agent Chat</title>
  <style nonce="${nonce}">
    * { box-sizing: border-box; }
    body { margin: 0; height: 100vh; display: flex; flex-direction: column; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); }
    header { padding: 10px 14px; border-bottom: 1px solid var(--vscode-panel-border); }
    header strong { display: block; font-size: 13px; }
    #status { color: var(--vscode-descriptionForeground); font-size: 11px; margin-top: 3px; }
    #task-card { padding: 8px 14px; border-bottom: 1px solid var(--vscode-panel-border); background: var(--vscode-sideBar-background); max-height: 42vh; overflow-y: auto; }
    #task-card details > summary { cursor: pointer; display: flex; gap: 8px; align-items: baseline; }
    #task-title { font-weight: 600; flex: 1; overflow-wrap: anywhere; }
    #task-state { color: var(--vscode-descriptionForeground); font-size: 11px; text-transform: uppercase; }
    .task-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px 16px; padding: 10px 0 2px; }
    .task-section strong { display: block; font-size: 11px; margin-bottom: 3px; text-transform: uppercase; color: var(--vscode-descriptionForeground); }
    .task-section ol, .task-section ul { margin: 0; padding-left: 20px; }
    .task-section li { margin: 2px 0; overflow-wrap: anywhere; }
    #task-terminal { margin-top: 8px; padding-left: 8px; border-left: 2px solid var(--vscode-focusBorder); color: var(--vscode-descriptionForeground); }
    #messages { flex: 1; overflow-y: auto; padding: 14px; }
    .message { margin: 0 0 12px; padding: 10px 12px; border-radius: 6px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.45; }
    .user { margin-left: 12%; background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border, transparent); }
    .assistant { margin-right: 5%; background: var(--vscode-sideBar-background); }
    .system { color: var(--vscode-descriptionForeground); border-left: 2px solid var(--vscode-focusBorder); padding: 6px 10px; }
    .error { color: var(--vscode-errorForeground); border: 1px solid var(--vscode-inputValidation-errorBorder); background: var(--vscode-inputValidation-errorBackground); }
    .meta { color: var(--vscode-descriptionForeground); font-size: 11px; margin-bottom: 5px; }
    pre { white-space: pre; overflow-x: auto; padding: 10px; background: var(--vscode-textCodeBlock-background); border: 1px solid var(--vscode-panel-border); font-family: var(--vscode-editor-font-family); font-size: var(--vscode-editor-font-size); }
    footer { padding: 10px; border-top: 1px solid var(--vscode-panel-border); background: var(--vscode-sideBar-background); }
    textarea { width: 100%; min-height: 72px; max-height: 220px; resize: vertical; padding: 8px; color: var(--vscode-input-foreground); background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border); font-family: inherit; }
    .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
    button { border: 0; padding: 6px 12px; color: var(--vscode-button-foreground); background: var(--vscode-button-background); cursor: pointer; }
    button:hover { background: var(--vscode-button-hoverBackground); }
    button.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
    button:disabled { opacity: 0.55; cursor: default; }
    [hidden] { display: none !important; }
  </style>
</head>
<body>
  <header><strong>BSAM Agent</strong><div id="status">Starting guarded local chat…</div></header>
  <section id="task-card" hidden>
    <details open>
      <summary><span id="task-title">Current task</span><span id="task-state"></span></summary>
      <div class="task-grid">
        <div class="task-section"><strong>Plan</strong><ol id="task-plan"></ol></div>
        <div class="task-section"><strong>Tool activity</strong><ol id="task-activity"></ol></div>
        <div class="task-section"><strong>Evidence</strong><ul id="task-evidence"></ul></div>
        <div class="task-section"><strong>Assumptions</strong><ul id="task-assumptions"></ul></div>
        <div class="task-section"><strong>Hypotheses</strong><ul id="task-hypotheses"></ul></div>
        <div class="task-section"><strong>Completion</strong><ul id="task-completion"></ul></div>
        <div class="task-section"><strong>Authorization</strong><ul id="task-authorization"></ul></div>
        <div class="task-section"><strong>Task workspace</strong><ul id="task-workspace"></ul></div>
      </div>
      <div id="task-terminal" hidden></div>
    </details>
  </section>
  <main id="messages" aria-live="polite"></main>
  <footer>
    <textarea id="input" aria-label="Message" placeholder="Ask about a workspace-local BSAM model. Ctrl+Enter sends." disabled></textarea>
    <div class="actions">
      <button id="cancel" class="secondary" hidden>Cancel pending action</button>
      <button id="confirm" hidden>Confirm reviewed action</button>
      <button id="send" disabled>Send</button>
    </div>
  </footer>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const messages = document.getElementById('messages');
    const status = document.getElementById('status');
    const input = document.getElementById('input');
    const send = document.getElementById('send');
    const confirm = document.getElementById('confirm');
    const cancel = document.getElementById('cancel');
    const taskCard = document.getElementById('task-card');
    const taskTitle = document.getElementById('task-title');
    const taskState = document.getElementById('task-state');
    const taskPlan = document.getElementById('task-plan');
    const taskActivity = document.getElementById('task-activity');
    const taskEvidence = document.getElementById('task-evidence');
    const taskAssumptions = document.getElementById('task-assumptions');
    const taskHypotheses = document.getElementById('task-hypotheses');
    const taskCompletion = document.getElementById('task-completion');
    const taskAuthorization = document.getElementById('task-authorization');
    const taskWorkspace = document.getElementById('task-workspace');
    const taskTerminal = document.getElementById('task-terminal');
    let busy = true;
    let pending = false;

    function append(role, text, meta) {
      const wrapper = document.createElement('div');
      wrapper.className = 'message ' + role;
      if (meta) {
        const label = document.createElement('div');
        label.className = 'meta';
        label.textContent = meta;
        wrapper.appendChild(label);
      }
      const content = document.createElement('div');
      content.textContent = String(text || '');
      wrapper.appendChild(content);
      messages.appendChild(wrapper);
      messages.scrollTop = messages.scrollHeight;
      return wrapper;
    }

    function fillTaskList(element, values, format, emptyText) {
      element.replaceChildren();
      const items = Array.isArray(values) && values.length ? values : [emptyText];
      for (const value of items) {
        const item = document.createElement('li');
        item.textContent = typeof value === 'string' ? value : format(value || {});
        element.appendChild(item);
      }
    }

    function detailText(details) {
      if (!details || typeof details !== 'object') return '';
      return Object.entries(details).map(([key, value]) => {
        const rendered = typeof value === 'object' ? JSON.stringify(value) : String(value);
        return key.replaceAll('_', ' ') + '=' + rendered;
      }).join(', ');
    }

    function renderTask(task) {
      if (!task || typeof task !== 'object') {
        taskCard.hidden = true;
        return;
      }
      taskCard.hidden = false;
      taskTitle.textContent = String(task.objective || 'Current engineering task');
      taskState.textContent = String(task.status || 'unknown');
      fillTaskList(taskPlan, task.plan, (item) => String(item), 'No explicit plan');
      fillTaskList(taskActivity, task.activity, (item) =>
        String(item.index || '?') + '. ' + String(item.tool || 'unknown') + ' - ' + String(item.status || 'unknown'),
      'No tool activity');
      fillTaskList(taskEvidence, task.evidence, (item) => {
        const details = detailText(item.details);
        return String(item.id || 'evidence') + ' - ' + String(item.tool || 'unknown')
          + (details ? ' - ' + details : '');
      }, 'No evidence recorded');
      fillTaskList(taskAssumptions, task.assumptions, (item) => String(item), 'No assumptions');
      fillTaskList(taskHypotheses, task.hypotheses, (item) => {
        const support = Array.isArray(item.supporting_evidence) ? item.supporting_evidence.join(', ') : '';
        const refute = Array.isArray(item.refuting_evidence) ? item.refuting_evidence.join(', ') : '';
        return String(item.status || 'open') + ': ' + String(item.statement || '')
          + (support ? ' [supports: ' + support + ']' : '')
          + (refute ? ' [refutes: ' + refute + ']' : '');
      }, 'No active hypotheses');
      const remaining = new Set(Array.isArray(task.remaining_criteria) ? task.remaining_criteria : []);
      fillTaskList(taskCompletion, task.completion_criteria, (item) => String(item), 'No completion criteria');
      for (const item of taskCompletion.children) {
        item.textContent = (remaining.has(item.textContent) ? 'Pending: ' : 'Satisfied: ') + item.textContent;
      }
      const authorization = task.authorization && typeof task.authorization === 'object'
        ? task.authorization : {};
      fillTaskList(taskAuthorization, [
        'Mode: ' + String(authorization.mode || 'read_only'),
        'Status: ' + String(authorization.status || 'unknown'),
        'Operations: ' + (Array.isArray(authorization.operations) ? authorization.operations.join(', ') : 'read'),
        'Runs: ' + String(authorization.executions_used || 0) + '/' + String(authorization.max_executions || 0),
      ], (item) => String(item), 'No authorization state');
      const workspace = task.task_workspace && typeof task.task_workspace === 'object'
        ? task.task_workspace : {};
      fillTaskList(taskWorkspace, [
        'State: ' + String(workspace.state || 'unavailable'),
        'Root: ' + String(workspace.root || 'not allocated'),
      ], (item) => String(item), 'No task workspace');
      taskTerminal.hidden = !task.terminal_reason;
      taskTerminal.textContent = task.terminal_reason ? 'Terminal reason: ' + String(task.terminal_reason) : '';
    }

    function setControls() {
      input.disabled = busy;
      send.disabled = busy || !input.value.trim();
      confirm.hidden = !pending;
      cancel.hidden = !pending;
      confirm.disabled = busy;
      cancel.disabled = busy;
      if (!busy) input.focus();
    }

    function submit(text) {
      const value = String(text || '').trim();
      if (!value || busy) return;
      append('user', value, 'You');
      input.value = '';
      busy = true;
      setControls();
      status.textContent = 'Working through guarded routing…';
      vscode.postMessage({ command: 'send', text: value });
    }

    send.addEventListener('click', () => submit(input.value));
    confirm.addEventListener('click', () => submit('/confirm'));
    cancel.addEventListener('click', () => submit('/cancel'));
    input.addEventListener('input', setControls);
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && event.ctrlKey) {
        event.preventDefault();
        submit(input.value);
      }
    });

    window.addEventListener('message', (event) => {
      const message = event.data || {};
      if (message.type === 'ready') {
        busy = false;
        pending = Boolean(message.pending_confirmation);
        status.textContent = message.provider + ' · ' + message.model
          + (message.reasoning_effort ? ' · ' + message.reasoning_effort : '')
          + ' · ' + message.phase;
        append('system', 'Connected to guarded BSAM routing for ' + message.workspace + '.');
        if (pending) append('system', 'The resumed session has an action awaiting confirmation.');
        renderTask(message.task);
      } else if (message.type === 'busy') {
        busy = Boolean(message.busy);
      } else if (message.type === 'turn') {
        busy = false;
        const turn = message.turn || {};
        pending = Boolean(turn.requires_confirmation);
        const wrapper = append('assistant', turn.message, turn.tool ? turn.phase + ' · ' + turn.tool : turn.phase);
        const result = turn.tool_result;
        if (result && typeof result.source_diff === 'string' && result.source_diff) {
          const diff = document.createElement('pre');
          diff.textContent = result.source_diff;
          wrapper.appendChild(diff);
        }
        renderTask(message.task);
        status.textContent = pending ? 'Review required · confirmation pending' : String(turn.phase || 'Ready');
      } else if (message.type === 'error') {
        busy = false;
        append('error', message.message, 'Local chat error');
        status.textContent = 'Error';
      } else if (message.type === 'closed') {
        busy = true;
        pending = false;
        append('system', message.message);
        status.textContent = 'Chat process stopped';
      }
      setControls();
    });
  </script>
</body>
</html>`;
  }
}
