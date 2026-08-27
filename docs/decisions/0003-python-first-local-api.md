# ADR 0003: Python-first core and local API

- Status: Proposed
- Date: 2026-08-27

## Context

The current machine has Python 3.10.11 but no Node.js. The final VS Code extension will require Node.js and TypeScript, while the core must also support CLI and automated testing independently of the editor.

## Decision

Implement the initial core and loopback Agent API in Python. Implement the later VS Code extension as a thin TypeScript client.

This remains proposed until G1 confirms there is no compelling dependency or deployment constraint that changes the choice.

## Consequences

- G1 specification work requires no new runtime installation.
- G2 can begin with the installed Python runtime.
- Node.js installation is deferred to the extension milestone.
- API contract tests become important because the extension and core use different languages.
