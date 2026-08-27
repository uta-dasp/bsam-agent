# Local-data and provider policy

## Default rule

BSAM source code, full input decks, VTMS files, material libraries, mesh data, output artifacts, filesystem paths, and proprietary engineering descriptions remain local.

The application must work with model providers disabled.

## External providers

An external provider may receive only a payload that has passed an explicit local redaction/sanitization policy. Free-tier Gemini must be treated as unsuitable for real BSAM/source/project data. Paid provider use does not remove the need for payload minimization, local configuration, and user-visible provider state.

API keys:

- are loaded from environment variables or an operating-system credential store;
- are never stored in model files, generated decks, logs, or Git;
- are redacted from errors and diagnostics.

## Local providers

Allowed local model families are limited to providers approved by the project owner. The initial allowlist may include Google Gemma and Meta Llama families. Chinese-origin model families are excluded.

A local provider still receives only the bounded context needed for its task. This reduces prompt size and prevents accidental coupling to raw source layout.

## Network posture

- Local API binds to loopback by default.
- No telemetry is enabled by default.
- Network provider calls are disabled unless a provider is explicitly configured.
- BSAM-specific internet search is prohibited.
- Source or artifact upload endpoints are not part of the Agent API.

## Audit metadata

Record provider name, model identifier, policy version, schema version, timestamp, tool calls, and payload digests. Do not record raw sensitive prompts by default.
