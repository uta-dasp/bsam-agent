# Development environment baseline

Observed on 2026-08-27.

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
| Node.js/npm | Not installed | Required later for the VS Code extension |
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

Use Python for the first core and local HTTP API because it is already installed and supports process supervision, schema validation, parsing, and test tooling. Add Node.js only when the VS Code extension milestone begins. This is a reversible choice because the editor communicates through the documented Agent API.
