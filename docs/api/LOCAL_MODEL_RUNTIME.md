# Local model runtime

The pinned runtime is llama.cpp b10621 (`v0.3.0`, commit `c1d0e7a0`). Meta Llama 4 Scout Q4_K_M is the provisional guarded-chat model; Meta Llama 3.1 8B remains a transport baseline. Scout did not pass the raw autonomous-routing gate, so deterministic orchestration—not model text—owns authorization and execution. Exact provenance and checksums are in `config/model-profiles/`. Model weights and the machine-local provider configuration remain outside Git.

## Start the server

From PowerShell, create a session-only API key and start the runtime with a local model path. Supplying a file path prevents network model fetching; llama.cpp has no telemetry configured by BSAM Agent.

```powershell
$keyBytes = New-Object byte[] 32
$keyGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $keyGenerator.GetBytes($keyBytes) } finally { $keyGenerator.Dispose() }
$env:BSAM_LOCAL_API_KEY = -join ($keyBytes | ForEach-Object { $_.ToString("x2") })
$runtime = "D:\Partha\BSAM\runtimes\llama.cpp\b10621\llama-server.exe"
$model = "D:\Partha\BSAM\models\meta-llama-4-scout-17b-16e-instruct\Llama-4-Scout-17B-16E-Instruct-Q4_K_M.gguf"
& $runtime --model $model --host 127.0.0.1 --port 18080 `
  --api-key $env:BSAM_LOCAL_API_KEY -t 24 -tb 24 -c 4096 -np 1 `
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

For Scout on this CPU, the default repacked mode is preferred: it used about 108 GiB but was materially faster, and the host has 512 GiB. `--no-repack` reduced observed peak memory to about 63 GiB but made responses substantially slower. `--skip-chat-parsing` is needed only for the native-tool experiment, not the selected structured-decision path.

## Security boundary

- Use only `127.0.0.1`, never `0.0.0.0` or a LAN address.
- Keep `credential_reference` as an environment-variable reference; never put a key in JSON.
- Use `--model` with the verified local GGUF; do not use remote model identifiers.
- The adapter validates all returned tool names and arguments before any deterministic dispatcher can receive them.
