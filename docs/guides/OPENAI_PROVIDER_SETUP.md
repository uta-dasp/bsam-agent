# OpenAI provider setup without exposing the BSAM library

This optional configuration uses OpenAI only to interpret the text typed into BSAM Agent chat. Parsing, registry lookup, validation, diff generation, file writes, confirmation, and BSAM execution stay local.

## Privacy boundary

The adapter sends:

- the text you type into the chat box;
- a compact routing instruction and selected deterministic tool contracts;
- up to eight bounded prior chat messages containing typed text and structured routing decisions.
- compact multi-step observation metadata such as digests, counts, validation summaries, and
  completion state. Hosted observations omit deck/diff/log text and entity identities.

It does **not** send:

- BSAM repository source code, library files, or internal documentation;
- input decks, include files, `.ele` meshes, VTMS/material libraries, output files, or run artifacts;
- file contents returned by inspect/validate/change/run tools;
- the capability registry's parameter catalog;
- the API key in the request body, logs, configuration, or conversation file.

The OpenAI adapter has no filesystem or local Agent API access. It receives only the message tuple assembled by the orchestrator. Returned output is untrusted: deterministic local code validates the tool name and arguments, confines paths to the workspace, requires review and separate confirmation before a model-changing apply, and enforces bounded task authorization for explicitly requested full runs or controlled stops.

`store` is fixed to `false` in both configuration validation and the actual HTTP request. This prevents normal Responses application-state storage. It does not promise zero retention: OpenAI documents that standard API abuse-monitoring logs may be retained for up to 30 days unless an account has approved stricter data controls. OpenAI also states that API data is not used to train its models unless the organization explicitly opts in.

Important: your typed text is sent to OpenAI. Do not paste BSAM source/library code, documentation, deck contents, mesh rows, or proprietary results into the chat box. Ask the agent to inspect a local path instead; the deterministic tool performs that work locally and returns only a local UI summary.

## 1. Update and install

From PowerShell:

```powershell
cd "D:\Partha\BSAM\bsam agent"
git pull --ff-only

cd clients\vscode
npm ci
npm test
npm run package
code --install-extension .\bsam-agent-0.6.0.vsix --force
```

Restart VS Code after installation.

## 2. Create the OpenAI API key

1. Sign in to the [OpenAI API platform](https://platform.openai.com/).
2. Configure API billing and project limits. A ChatGPT subscription does not automatically provide API credit.
3. Open [API keys](https://platform.openai.com/api-keys), create a project key, and copy it once.
4. Never paste the key into BSAM chat, a JSON file, source control, or a shell command saved in history.

The repository reads only an environment reference named `OPENAI_API_KEY`.

## 3. Create the ignored provider configuration

From the repository root:

```powershell
Copy-Item config\provider.openai.example.json config\provider.openai.json
```

The resulting ignored file contains no secret:

```json
{
  "provider": "openai",
  "model": "gpt-5.6-terra",
  "endpoint": "https://api.openai.com",
  "credential_reference": "env:OPENAI_API_KEY",
  "timeout_seconds": 120,
  "max_input_characters": 24000,
  "max_output_tokens": 2048,
  "data_policy": "sanitized",
  "store": false,
  "reasoning_effort": "high"
}
```

Do not change the endpoint. Configuration loading rejects another host, a URL containing credentials/options, `local-private`, a missing credential reference, or `store: true` before the chat can start.

## 4. Configure VS Code

Open VS Code Settings (JSON) for this workspace and add:

```json
{
  "bsamAgent.repositoryRoot": "D:\\Partha\\BSAM\\bsam agent",
  "bsamAgent.workspaceRoot": "D:\\Partha\\BSAM",
  "bsamAgent.chat.providerConfigPath": "config/provider.openai.json",
  "bsamAgent.provider": "openai",
  "bsamAgent.model": "gpt-5.6-terra",
  "bsamAgent.reasoningEffort": "high",
  "bsamAgent.chat.auditEnabled": true
}
```

The workspace settings file is locally ignored by this repository. Do not add the key itself to settings.
The extension always prompts for `OPENAI_API_KEY` when `bsamAgent.provider` is `openai`; it does not
read an API key from settings. `gpt-5.6-sol` can be selected by changing only the model setting.

## 5. Open the chat safely

1. Open the Command Palette with `Ctrl+Shift+P`.
2. Run `BSAM Agent: Open Chat Window`.
3. Paste the API key into the VS Code password prompt labeled `OPENAI_API_KEY`.
4. The extension passes it only in the environment of the local Python chat subprocess; it does not persist the key.
5. Start with a non-sensitive routing check such as `What deterministic operations can you help me perform?`

For normal work, refer to files by local path, for example:

```text
Inspect projects/notch_v1/notch_v1.in and summarize validation errors.
```

Do not paste the file contents. Inspection and summarization for recognized deterministic requests happen locally. Review every diff, and use `/confirm` only after the proposed local action is correct.

## 6. Terminal alternative

The VS Code password prompt is preferred. For a terminal-only session, enter the key without placing it in command history:

```powershell
cd "D:\Partha\BSAM\bsam agent"
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
  $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
  Remove-Variable keyPointer, secureKey
}
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent chat `
  --workspace-root "D:\Partha\BSAM" `
  --config config\provider.openai.json `
  --provider openai `
  --model gpt-5.6-terra `
  --reasoning-effort high `
  --session .bsam-agent\conversations\openai.json
Remove-Item Env:OPENAI_API_KEY
```

Omit `--session` if you do not want a local raw chat transcript. Digest-only audit records are enabled by default; add `--no-audit` to disable those too.

## 7. Switch back to fully local chat

Change the provider setting back to the local provider. The model can be omitted to use the local
provider configuration:

```json
{
  "bsamAgent.chat.providerConfigPath": "config/provider.local.json",
  "bsamAgent.provider": "cpu-local",
  "bsamAgent.model": "",
  "bsamAgent.reasoningEffort": "",
  "bsamAgent.chat.credentialEnvironment": "BSAM_LOCAL_API_KEY"
}
```

Then start the pinned loopback model runtime and reopen the chat. The deterministic core is identical in both modes.

## Troubleshooting

- `credential environment variable is not set: OPENAI_API_KEY`: reopen the chat and enter the key in the password prompt; confirm the VS Code credential setting is exactly `OPENAI_API_KEY`.
- `OpenAI provider returned HTTP 401`: the key is missing, invalid, expired, or belongs to the wrong project.
- `OpenAI provider returned HTTP 400`: confirm the model ID and inspect the bounded `code`/`param` detail. The adapter uses Responses JSON mode, then validates the exact decision and tool schemas locally.
- `OpenAI provider returned HTTP 429`: check project billing/rate limits and retry later.
- `openai provider requires store=false`: restore `"store": false` in the ignored provider JSON.
- `openai provider endpoint must be https://api.openai.com`: restore the exact official endpoint without `/v1`.
- A recognized inspect/change/validate/run request produces no OpenAI usage: expected. Deterministic fast paths execute locally without calling a model.

## Official OpenAI references

- [API quickstart](https://developers.openai.com/api/docs/quickstart)
- [Responses create API](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [API data controls and retention](https://developers.openai.com/api/docs/guides/your-data)
