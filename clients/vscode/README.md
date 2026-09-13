# BSAM Agent for VS Code

This extension is a thin client for the loopback-only deterministic BSAM Agent API. It does not parse, modify, validate, or execute BSAM models itself.

The client manages an extension-owned API process, validates or inspects the active model, browses registry-derived capability status, previews registered parameter changes, applies reviewed plans, and controls isolated BSAM runs. `.ele` files route through the strict mesh importer rather than deck validation. The client verifies that an existing API owns the same resolved workspace root before sending any model path.

## Guarded workflows

- `BSAM Agent: Preview Parameter Change` derives editable root-deck occurrences and parameters from the semantic model plus registry operation status. The core validates the selected value, writes a revision-bound plan, and returns a unified diff for review. Verified repeated parameters offer explicit occurrence selection and append behavior.
- `BSAM Agent: Apply Last Reviewed Change` revalidates the stored plan identity and source revision, displays the diff again, and requires modal confirmation before writing a new deck and audit sidecar.
- `BSAM Agent: Run Current Model` publishes validation diagnostics first, requires a workspace-local executable and modal confirmation, and reserves a new isolated output directory.
- `BSAM Agent: Show Last Run Status` and `BSAM Agent: Stop Last Run` read durable status or request BSAM's controlled stop path. The extension never directly kills a BSAM run.
- `BSAM Agent: Open Local Chat` opens the existing guarded chat client in a persistent VS Code terminal. It reuses the same local provider configuration, saved conversation state, digest audit, reviewed diffs, and separate `/confirm` turn as the CLI.

## Development

Use the verified portable Node.js 24.21.0 toolchain recorded in `docs/DEVELOPMENT_ENVIRONMENT.md`, or another compatible Node.js installation:

```powershell
cd clients\vscode
npm ci
npm test
npm run package
```

Press F5 from this folder to launch an Extension Development Host after compilation.

Install the packaged client into VS Code with:

```powershell
code --install-extension .\bsam-agent-0.4.0.vsix
```

Open the Command Palette and run `BSAM Agent: Start Local API`. The extension defaults the API workspace to the first open folder; set `bsamAgent.workspaceRoot` to an absolute path when a broader include boundary is required.

Set `bsamAgent.executablePath` to an executable inside that workspace boundary to avoid selecting it for each run. The configured BSAM timeout and controlled-stop grace period are passed to the deterministic supervisor.

An installed VSIX auto-detects the BSAM Agent repository when the open folder is either the repository itself or its parent. Set `bsamAgent.repositoryRoot` only when it is elsewhere. Local chat defaults to `config/provider.local.json` and `.bsam-agent/conversations/vscode.json`; start the configured loopback model server first. If VS Code did not inherit `BSAM_LOCAL_API_KEY`, the command requests it in a password field and passes it only to that terminal process.
