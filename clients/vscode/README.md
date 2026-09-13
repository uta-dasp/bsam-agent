# BSAM Agent for VS Code

This extension is a thin client for the loopback-only deterministic BSAM Agent API. It does not parse, modify, validate, or execute BSAM models itself.

Initial commands manage an extension-owned API process, validate or inspect the active model, browse registry-derived capability status, and show the extension log. `.ele` files route through the strict mesh importer rather than deck validation. The client verifies that an existing API owns the same resolved workspace root before sending any model path.

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
code --install-extension .\bsam-agent-0.1.0.vsix
```

Open the Command Palette and run `BSAM Agent: Start Local API`. The extension defaults the API workspace to the first open folder; set `bsamAgent.workspaceRoot` to an absolute path when a broader include boundary is required.
