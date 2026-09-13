# Using BSAM Agent chat in VS Code

This tutorial covers the dedicated local-model chat window included with BSAM Agent for VS Code 0.5.0. The command opens a theme-aware panel beside the editor. A private local process uses the same guarded orchestrator as `python -m bsam_agent chat`; users do not interact with its command line.

The language model only interprets requests. Deterministic BSAM Agent code resolves registry capabilities, validates paths and values, creates review plans, and performs tool calls. Applying a change, starting a run, or requesting a stop always requires a separate confirmation turn.

## 1. Confirm the installed components

The following paths are present on the current BSAM workstation:

```text
VS Code extension: uta-dasp.bsam-agent 0.5.0
Repository:        D:\Partha\BSAM\bsam agent
Python:            C:\Program Files\Python310\python.exe
llama.cpp server:  D:\Partha\BSAM\runtimes\llama.cpp\b10621\llama-server.exe
Local model:       D:\Partha\BSAM\models\meta-llama-4-scout-17b-16e-instruct\Llama-4-Scout-17B-16E-Instruct-Q4_K_M.gguf
BSAM executable:   D:\Partha\BSAM\projects\bsam20.exe
Provider config:   D:\Partha\BSAM\bsam agent\config\provider.local.json
```

Check the extension from PowerShell:

```powershell
code --list-extensions --show-versions | Select-String "uta-dasp.bsam-agent"
```

Expected result:

```text
uta-dasp.bsam-agent@0.5.0
```

If it is missing, install the already-built package:

```powershell
code --install-extension "D:\Partha\BSAM\bsam agent\clients\vscode\bsam-agent-0.5.0.vsix" --force
```

Then run `Developer: Reload Window` from the VS Code Command Palette.

## 2. Open the correct workspace

Open the parent BSAM directory, not only the agent repository:

```powershell
code "D:\Partha\BSAM"
```

Using `D:\Partha\BSAM` as the workspace lets the guarded API reach both `projects` and `bsam agent` without allowing paths outside that boundary. The extension automatically detects the repository in the `bsam agent` child folder.

Recommended workspace settings are shown below. In VS Code, open Settings JSON with `Preferences: Open Workspace Settings (JSON)` and add:

```json
{
  "bsamAgent.workspaceRoot": "D:\\Partha\\BSAM",
  "bsamAgent.repositoryRoot": "D:\\Partha\\BSAM\\bsam agent",
  "bsamAgent.pythonPath": "C:\\Program Files\\Python310\\python.exe",
  "bsamAgent.executablePath": "D:\\Partha\\BSAM\\projects\\bsam20.exe",
  "bsamAgent.chat.providerConfigPath": "config/provider.local.json",
  "bsamAgent.chat.sessionPath": ".bsam-agent/conversations/vscode.json",
  "bsamAgent.chat.credentialEnvironment": "BSAM_LOCAL_API_KEY",
  "bsamAgent.chat.auditEnabled": true,
  "bsamAgent.runTimeoutSeconds": 3600,
  "bsamAgent.stopGraceSeconds": 30
}
```

The explicit repository setting is optional on this directory layout, but makes troubleshooting simpler. The session and audit locations are ignored by Git because the transcript can contain raw model or project text.

## 3. Check the local provider configuration

The machine-local file `config/provider.local.json` should contain a loopback provider similar to:

```json
{
  "provider": "cpu-local",
  "model": "Llama-4-Scout-17B-16E-Instruct-Q4_K_M",
  "endpoint": "http://127.0.0.1:18080",
  "credential_reference": "env:BSAM_LOCAL_API_KEY",
  "timeout_seconds": 300,
  "max_input_characters": 24000,
  "max_output_tokens": 2048,
  "data_policy": "local-private"
}
```

Do not put an API key in this JSON. `config/provider.local.json` is intentionally not committed.

If the file does not exist on another checkout, copy the example and then select the locally installed model name:

```powershell
Copy-Item config\provider.local.example.json config\provider.local.json
```

## 4. Start the local model server

Open a separate PowerShell terminal. Generate a new session-only key, copy it for the VS Code prompt, and start the pinned local server:

```powershell
$keyBytes = New-Object byte[] 32
$keyGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $keyGenerator.GetBytes($keyBytes) } finally { $keyGenerator.Dispose() }
$env:BSAM_LOCAL_API_KEY = -join ($keyBytes | ForEach-Object { $_.ToString("x2") })
$env:BSAM_LOCAL_API_KEY.Length
Set-Clipboard -Value $env:BSAM_LOCAL_API_KEY

$runtime = "D:\Partha\BSAM\runtimes\llama.cpp\b10621\llama-server.exe"
$model = "D:\Partha\BSAM\models\meta-llama-4-scout-17b-16e-instruct\Llama-4-Scout-17B-16E-Instruct-Q4_K_M.gguf"
& $runtime --model $model --host 127.0.0.1 --port 18080 `
  --api-key $env:BSAM_LOCAL_API_KEY -t 24 -tb 24 -c 4096 -np 1 `
  --jinja --no-slots
```

The length should be `64`. Keep this server terminal open. Wait until llama.cpp reports that it is listening on `127.0.0.1:18080`.

Security rules:

- Bind only to `127.0.0.1`; do not use `0.0.0.0` or a LAN address.
- Use the verified local GGUF path. Do not specify a remote model identifier.
- Never save the key in provider JSON, workspace settings, source files, or chat messages.
- Clear the clipboard after the VS Code credential prompt with `Set-Clipboard -Value ""`.

## 5. Open the BSAM Agent chat window

In VS Code:

1. Press `Ctrl+Shift+P`.
2. Run `BSAM Agent: Open Chat Window`.
3. If prompted for `BSAM_LOCAL_API_KEY`, paste the 64-character value copied from the server terminal and press Enter. The password field hides it and the extension passes it only to the private local chat process.
4. Clear the clipboard in the server PowerShell.

The chat panel opens beside the editor. Its header shows the connected local model and conversation phase. The lower area contains a multiline prompt box, Send button, and confirmation controls that appear only when a guarded action is pending. Use `Ctrl+Enter` to send.

Running `BSAM Agent: Open Chat Window` again focuses the existing panel. Close that panel before reopening it with a different credential or configuration.

The chat command does not require `BSAM Agent: Start Local API`; chat constructs its guarded local API in its private process. The Start Local API command is used by editor diagnostics, forms, diffs, and direct run commands.

## 6. Start with read-only requests

Use workspace-relative paths. A safe first request is:

```text
Inspect projects/TriC_v311/TriC_v311.in and summarize its model, boundary conditions, mesh, errors, and warnings.
```

Other read-only examples:

```text
Validate projects/TriC_v311/TriC_v311.in.
```

```text
List the registered capabilities used by projects/notch_v1/notch_v1.in.
```

```text
Show the effective d_reduction value in projects/notch_v1/notch_v1.in.
```

Read-only inspection and validation do not require `/confirm`.

Scout commonly takes roughly 20–30 seconds per routed request on this CPU host. Do not submit the same request repeatedly while one response is being generated.

## 7. Preview and apply a model change

Ask for one exact registered edit and explicitly require a new file:

```text
Change d_reduction in projects/notch_v1/notch_v1.in to 0.45 and create a new file. Do not overwrite the original.
```

Expected workflow:

1. The orchestrator resolves `d_reduction` through the capability registry.
2. Deterministic code inspects and validates the source.
3. It creates a source-revision-bound plan and prints the unified diff.
4. Chat reports the proposed new destination and waits for a separate confirmation.
5. Review the path, parameter value, and every changed line.
6. Type `/confirm` only if the proposal is correct:

```text
/confirm
```

The apply step writes a new deck plus an audit sidecar. It does not overwrite the original deck. If the default destination already exists, cancel and request another unique destination.

To reject the pending operation, type:

```text
/cancel
```

Important: when an action is waiting for confirmation, a new non-confirmation request cancels that pending action. Confirm or cancel it before starting unrelated work.

For a preview without immediate application:

```text
Preview changing d_reduction in projects/notch_v1/notch_v1.in to 0.45, but do not apply it.
```

Later, refer to the exact remembered plan:

```text
Apply that reviewed change to projects/notch_v1/notch_v1.chat-045.in.
```

Chat will still require `/confirm`.

## 8. Refresh a stale plan

Plans are bound to the complete source-set digest. If the root deck or any included file changes after preview, application is blocked.

Ask:

```text
Refresh the stale plan against the current source.
```

The core replays the typed request, creates a new plan and digest, shows a new diff, and requires a new `/confirm`. Never assume the earlier diff still applies.

## 9. Start, monitor, and stop a BSAM run through chat

Use a new output directory and explicitly name the executable:

```text
Run projects/TriC_v311/TriC_v311.in in .bsam-agent/runs/tric-chat-tutorial with projects/bsam20.exe and a 3600 second timeout.
```

Review the proposed source, executable, timeout, and output directory. Then type:

```text
/confirm
```

Starting a run is asynchronous. Request status with the same directory:

```text
Check status for .bsam-agent/runs/tric-chat-tutorial.
```

To request BSAM's controlled stop path:

```text
Stop the run in .bsam-agent/runs/tric-chat-tutorial.
```

Review the target and type `/confirm`. The chat tool requests BSAM's controlled `.exit` mechanism; it does not directly kill the process. The owning run supervisor may escalate only after the configured grace period.

Use a fresh output directory for every run. Existing run directories are deliberately rejected.

## 10. Use direct extension commands alongside chat

For deterministic editor workflows that do not need natural language:

1. Run `BSAM Agent: Start Local API`.
2. Open a `.in`, `.bsam`, or `.ele` file inside the configured workspace.
3. Use these Command Palette commands:

   - `BSAM Agent: Validate Current Model`
   - `BSAM Agent: Inspect Current Model`
   - `BSAM Agent: Preview Parameter Change`
   - `BSAM Agent: Apply Last Reviewed Change`
   - `BSAM Agent: Run Current Model`
   - `BSAM Agent: Show Last Run Status`
   - `BSAM Agent: Stop Last Run`

Deck diagnostics appear in the editor Problems collection. `.ele` files use the strict mesh importer. Parameter forms are derived from semantic occurrences and registry-verified edit support, then produce the same reviewable plans as chat.

## 11. Conversation persistence and privacy

The default local conversation state is:

```text
D:\Partha\BSAM\.bsam-agent\conversations\vscode.json
```

Digest-only chat audit records are stored beneath:

```text
D:\Partha\BSAM\.bsam-agent\audit
```

The session file contains raw chat text and pending-action state. Both locations remain local and are ignored by this repository. To begin an independent conversation without replacing the old state, change `bsamAgent.chat.sessionPath` to a new relative filename and reopen the chat panel.

No OpenAI or other hosted provider is enabled by this workflow. The provider endpoint is loopback-only and the model file is local.

## 12. Troubleshooting

### The command is missing

Confirm `uta-dasp.bsam-agent@0.5.0` is installed, then run `Developer: Reload Window`. Ensure the Command Palette entry begins with `BSAM Agent:`.

### Cannot locate the BSAM Agent repository

Set:

```json
"bsamAgent.repositoryRoot": "D:\\Partha\\BSAM\\bsam agent"
```

The selected directory must contain `src\bsam_agent`.

### Credential environment variable is not set

Close the existing BSAM chat panel and run `BSAM Agent: Open Chat Window` again. Paste the exact key used to start llama.cpp when the password prompt appears. The variable name is `BSAM_LOCAL_API_KEY` with no added slashes.

### HTTP 401 or unauthorized

The client and server keys differ. Generate a fresh key, restart llama.cpp with it, close the chat panel, and reopen chat using that same value.

### Connection refused at port 18080

The local model server is not running, is still loading, or is using a different port. Confirm `config/provider.local.json` points to `http://127.0.0.1:18080` and wait for the server to finish loading.

### Provider timeout

Scout is CPU-intensive. The current local config allows 300 seconds. Check the llama.cpp terminal for an active request before retrying. If required, increase `timeout_seconds` in the ignored machine-local provider config.

### Selected file is outside the workspace

Open `D:\Partha\BSAM` as the workspace or set `bsamAgent.workspaceRoot` to that absolute path. The boundary intentionally rejects `..` escapes and unrelated absolute paths.

### Port 8765 serves a different workspace

This affects direct extension commands, not the chat panel. Stop the other BSAM Agent API or make its workspace root match the current VS Code setting, then rerun `BSAM Agent: Start Local API`.

### Destination or run directory already exists

Choose a new path. BSAM Agent never overwrites an existing deck, audit file, plan, or run directory.

### A reviewed plan became stale

Ask chat to refresh the stale plan, inspect the new diff, and issue a fresh `/confirm`.

### View extension diagnostics

Run `BSAM Agent: Show Output` from the Command Palette. Also inspect the local-model server terminal for provider transport errors.

## 13. End the session

Send this from the chat window:

```text
/quit
```

This ends the private chat process while preserving the configured session file. Closing the chat panel does the same. Stop llama.cpp in its separate PowerShell with `Ctrl+C`, then clear any remaining clipboard copy of the session key.
