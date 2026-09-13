# Development environment baseline

Observed on 2026-08-27.

BSAM baseline re-audited on 2026-08-31: source `9954027f1c325c63d58aeb836e8fec41a4b363af`; executable SHA-256 `7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A`; executable build timestamp 2026-08-27 20:34:14. Four first-party SHEFF submodule worktrees were locally modified, so the executable hash—not the superproject commit alone—is the authoritative compiled-artifact identity. See [the baseline audit](bsam/BASELINE_AUDIT_2026-08-31.md).

## Machine

- Windows Server 2022 Standard, x64
- 2 × Intel Xeon E5-2687W v4 at 3.00 GHz
- 12 physical cores and 24 logical processors per socket
- 24 physical cores and 48 logical processors total
- 512 GiB installed RAM
- No GPU available for model inference

## Installed tools

| Tool | Observed version | Initial use |
|---|---:|---|
| Git | 2.36.1.windows.1 | Repository and version control |
| Python | 3.10.11 | Preferred core/API implementation baseline |
| .NET SDK | 5.0.416 | Present, not selected for the first implementation |
| Node.js/npm | Portable Node.js 24.21.0 LTS / npm 11.19.0 | VS Code extension build and test toolchain |
| Ollama | Not installed | Optional; not required for the deterministic core |
| Rust/Cargo | Not installed | Not required |

## CPU-local model direction

The RAM capacity permits large quantized models, but memory capacity is not the same as interactive speed. The first benchmark should compare a small and a medium non-Chinese model family using a local HTTP server, with strict JSON-schema/tool-call tests and realistic prompt sizes.

Preferred order:

1. Build and test the core without any model dependency.
2. Benchmark a llama.cpp-compatible local server with an allowed Gemma or Llama instruct model.
3. Select the smallest model that reliably emits the required typed intent and tool calls.
4. Add Gemini and OpenAI adapters only behind the same provider interface.

No local model runtime should be installed until the provider contract and evaluation cases exist.

## Tooling decision

Use Python for the core and local HTTP API because it supports process supervision, schema validation, parsing, and test tooling. The M6 VS Code extension uses a separate portable Node.js toolchain and remains a thin TypeScript client over the documented Agent API.

The M6 toolchain is stored outside the repository at `D:\Partha\BSAM\runtimes\node\node-v24.21.0-win-x64`. Its downloaded Windows x64 archive was verified before extraction with SHA-256 `158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541`. Extension dependencies are exactly pinned in `clients/vscode/package-lock.json`.
