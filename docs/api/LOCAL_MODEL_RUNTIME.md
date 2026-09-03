# Local model runtime

The pinned runtime is llama.cpp b10621 (`v0.3.0`, commit `c1d0e7a0`). Meta Llama 3.1 8B and Llama 4 Scout Q4_K_M are verified benchmark candidates, but neither passed chat acceptance. Exact provenance and checksums are in `config/model-profiles/`. Model weights and the machine-local provider configuration remain outside Git.

## Start the server

From PowerShell, create a session-only API key and start the runtime with a local model path. Supplying a file path prevents network model fetching; llama.cpp has no telemetry configured by BSAM Agent.

```powershell
$env:BSAM_LOCAL_API_KEY = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$runtime = "D:\Partha\BSAM\runtimes\llama.cpp\b10621\llama-server.exe"
$model = "D:\Partha\BSAM\models\meta-llama-3.1-8b-instruct\Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
& $runtime --model $model --host 127.0.0.1 --port 18080 `
  --api-key $env:BSAM_LOCAL_API_KEY -t 12 -tb 12 -c 8192 -np 1 `
  --jinja --no-slots
```

Keep that terminal open. The API key exists only in the current PowerShell process and is not written to the provider JSON.

## Verify and benchmark

In a second PowerShell opened from the first one (so it inherits the session key), run:

```powershell
Invoke-RestMethod http://127.0.0.1:18080/health `
  -Headers @{ Authorization = "Bearer $env:BSAM_LOCAL_API_KEY" }

cd "D:\Partha\BSAM\bsam agent"
$env:PYTHONPATH = "$PWD\src"
python scripts\benchmark_local_model.py `
  --config config\provider.local.json `
  --peak-working-memory-gib 5 `
  --output evals\results\llama-3.1-8b-q4_k_m.json
```

Replace the memory value with the measured peak working set of `llama-server`; it is an acceptance input, not a model claim. The result JSON is ignored because it can contain raw synthetic prompts and responses. Stop the server with Ctrl+C.

For Scout on this CPU, `--no-repack` reduced observed peak working memory substantially but made generation too slow for the acceptance gate. `--skip-chat-parsing` exposes Scout's native function-call text for the adapter's strict literal parser; it is an evaluation workaround for llama.cpp's incompatible PEG parser, not a model acceptance result.

## Security boundary

- Use only `127.0.0.1`, never `0.0.0.0` or a LAN address.
- Keep `credential_reference` as an environment-variable reference; never put a key in JSON.
- Use `--model` with the verified local GGUF; do not use remote model identifiers.
- The adapter validates all returned tool names and arguments before any deterministic dispatcher can receive them.
