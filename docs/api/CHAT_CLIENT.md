# Terminal chat client

The initial client uses Llama 4 Scout only to route language into bounded requests. Local deterministic code validates every argument, confines paths to the selected workspace, creates and reviews plans, requires a separate `/confirm` turn for apply/run/stop, and performs all authoritative work.

## Start and use

Start the pinned llama.cpp server as described in [Local model runtime](LOCAL_MODEL_RUNTIME.md), then use a second PowerShell with the same session API key:

```powershell
cd "D:\Partha\BSAM\bsam agent"
$env:PYTHONPATH = "$PWD\src"
python -m bsam_agent chat `
  --workspace-root "D:\Partha\BSAM" `
  --config config\provider.local.json `
  --session .bsam-agent\conversations\notch.json
```

`/confirm` executes exactly the pending guarded action, `/cancel` discards it, and `/quit` exits. A different provider configuration selects another model. The workspace root binds every tool path. The optional `--session` file saves raw local chat text and pending state so the conversation can resume; omit it for an ephemeral conversation. Digest-only audit metadata is enabled by default beneath `.bsam-agent/audit`; `--no-audit` disables it.

Preview and review responses display the deterministic source diff. Validation, apply, run, status, and stop responses are summarized from tool results rather than model claims. Run artifact directories are shown in the response.

## Current limitations and recovery

- Scout takes roughly 20–30 seconds for many routed requests on the CPU host.
- Only registered deterministic tools are available; unsupported BSAM operations remain unavailable through chat.
- Raw model routing is imperfect, so review every proposed tool and diff. No guarded action runs without a separate `/confirm`.
- If the model server is unavailable, restart it and repeat the request. If a saved state contains an unwanted pending action, resume it and use `/cancel`, or start without `--session`.
