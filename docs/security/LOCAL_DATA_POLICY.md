# Local-data and provider policy

## Default rule

BSAM source code, full input decks, Abaqus-style `.ele` files, VTMS files, material libraries, mesh data, output artifacts, filesystem paths, and proprietary engineering descriptions remain local.

The application must work with model providers disabled.

## External providers

An external provider may receive only a payload that has passed an explicit local redaction/sanitization policy. Free-tier Gemini must be treated as unsuitable for real BSAM/source/project data. Paid provider use does not remove the need for payload minimization, local configuration, and user-visible provider state.

API keys:

- are loaded from environment variables or an operating-system credential store;
- are never stored in model files, generated decks, logs, or Git;
- are redacted from errors and diagnostics.

The OpenAI adapter is routing-only. Its request builder has no filesystem or Agent API access and is passed only bounded chat messages. The orchestrator excludes the registry parameter catalog from hosted prompts; deterministic tools read and modify files locally after validating the returned routing decision. OpenAI configuration is restricted to the official HTTPS endpoint and `store: false`.

Typed chat text is external-provider data. Users must not paste BSAM source code, library documentation, full decks, mesh rows, or proprietary result data into hosted chat. Standard OpenAI API abuse-monitoring retention may still apply even when response storage is disabled.

During bounded multi-step routing, a hosted provider may receive compact deterministic observation
metadata: digests, counts, validation summaries, completed action names, and completion criteria.
The orchestrator excludes deck text, file diffs, log excerpts, and entity identities from that
hosted planning context. Evidence-grounded final synthesis receives the same sanitized context;
it cannot receive raw workspace matches or source excerpts merely because the task is complete.
Local-private source and artifacts remain in deterministic tools.

General workspace discovery is restricted to an allowlist of engineering/document text suffixes
and rejects hidden or credential-like files, blocked directories, binary/oversized content,
workspace escapes, and symbolic links. Local providers may receive bounded excerpts and literal
search matches. Hosted providers receive only counts and digests; file paths, text excerpts, and
match contents are removed from replanning context.

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
