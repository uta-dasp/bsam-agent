# Guarded TriC live-model and executable acceptance — 2026-09-12

## Scope

This acceptance exercised the provider-neutral chat orchestrator, Meta Llama 4 Scout, the deterministic confirmation boundary, asynchronous run supervision, and the pinned BSAM executable against the trusted non-notch `projects/TriC_v311/TriC_v311.in` deck. The source deck was read only. All generated artifacts were written to the ignored isolated directory `bsam agent/runs/tric-live-exec-20260912`.

The model server used the pinned llama.cpp b10621 runtime and the verified 65,359,899,808-byte Scout Q4_K_M file. It listened only on `127.0.0.1:18080` and was stopped after acceptance. The normal configuration supports a process-local API key. For this run, the execution guard would not pass an ephemeral key through the launcher, so a temporary ignored no-auth provider configuration was used while retaining the loopback-only bind. This does not qualify a network-exposed or unauthenticated production deployment.

## Guarded conversation

Scout mapped the run request to `run_bsam` with the exact source, executable, output directory, and 30-second timeout and returned `confirm=false`. No executable launched at that turn. A separate `/confirm` turn dispatched the action. Two subsequent natural-language status requests mapped to `get_run_status` and reported the running/pending and terminal/stopped states respectively.

The first routing response completed in about 41.6 seconds. The two status-routing responses completed in about 38.7 and 14.0 seconds. This small acceptance proves correct routing for these three turns, not the autonomous accuracy gate; Scout remains rejected by the broader benchmark. A hosted OpenAI-compatible provider can later use the same provider interface, tool schemas, deterministic policy, and confirmation boundary.

The live run revealed that terminal status results were summarized correctly but did not update the persisted task's `run_state`. Registry 0.137.0 closes that gap: `get_run_status` now persists each state and marks terminal stopped/succeeded runs complete while retaining failed/disrupted classifications as structured failures. A trajectory regression covers accepted, running, terminal, save, and restore state.

## Executable evidence

- Input size: 31,186,755 bytes
- Input SHA-256: `8EF5E12ED6687A0AF28BC79BD4C6672B51E7E6A70808E794EC4BDD1FD09E34A1`
- Source-set SHA-256: `3DDF5F3C50310557B115D3F12170D2EB2AEB499F9CDB9ACD86C14F670CD53ABA`
- Executable SHA-256: `7AE34D9821C6FE017897B020D615BFFA8A33F33F6D3734EBA3FD5A435788FB2A`
- Timeout: 30 seconds
- Total supervised duration: 51.724441 seconds
- Classification: `stopped`
- Process exit code: `0`
- Stop reason: `timeout`
- Stop escalation: false
- Fatal markers: none
- Success sentinel: absent
- Listing: 19,701 bytes, SHA-256 `2188F99FEF2E9AFEE444EE49209701D7D4F74FE0EACEE194DFAD50E1E715ECD8`
- TP artifact: 46,924,060 bytes, SHA-256 `746AF9AD701969ABCE9E1B1D8A40DA9DB93FFA41405A9CC99A012646138E31E0`
- Run manifest SHA-256: `52163A7116ADC75D8CF4641E5DDE62BAB5205B5D5FC2BB218B2D70A340BBAC2E`

BSAM completed input processing, matrix formation, PARDISO factorization and solution, and one converged loading step before observing the controlled stop request. This proves guarded launch, sustained non-notch execution, status, artifact capture, and clean timeout control. It does not claim full TriC analysis completion.
