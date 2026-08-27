# Local model recommendation

## Decision

Benchmark **Llama 4 Scout 17B-16E Instruct** in a 4-bit GGUF as the primary local model. Use **Llama 3.3 70B Instruct** in a 4-bit GGUF as the quality/control comparison, and **Llama 3.1 8B Instruct** in a 6-bit GGUF as the fast development model.

Do not adopt a model solely from published benchmark scores. The release gate is performance on the BSAM Agent's local, synthetic evaluation set: schema validity, tool-call accuracy, unsupported-capability refusal, edit-plan correctness, latency, and peak memory.

## Why this fits the workstation

The machine has 24 physical Broadwell-era Xeon cores, AVX2, no GPU, and 512 GiB RAM. It can hold large quantized models, but token generation will be constrained mainly by CPU memory bandwidth, dual-socket NUMA traffic, and serial generation latency.

Scout is a mixture-of-experts model with 17 billion activated parameters and 109 billion total parameters. It is therefore the most promising current Meta balance to test: much more model capacity than an 8B model without dense 70B compute on every token. This is a benchmark hypothesis, not a performance guarantee; expert-weight traffic can still be expensive on CPU.

Llama 3.3 70B is the mature reference for instruction following and function calling, but a dense CPU-only 70B model is likely to feel slow interactively. Llama 3.1 8B is suitable for rapid development and plumbing tests, but it should not be trusted to authorize or compose complex dependency-aware BSAM transformations without passing the same evaluations.

Llama 4 Maverick is out of scope for this workstation's first version: its 400-billion total parameter footprint creates no useful advantage for an interactive CPU-only starting point.

## Runtime

Use `llama.cpp` first. It supports AVX/AVX2 CPU inference, GGUF quantization, a local OpenAI-compatible HTTP server, and grammar/JSON-Schema-constrained output. Bind it only to loopback for the initial implementation. Keep the BSAM parser, registry, validator, renderer, runner, and approval policy deterministic; the model proposes typed intents and tool calls but never emits the authoritative deck directly.

Start benchmark contexts at 16K or 32K rather than advertising a model's maximum context. The agent should retrieve only the relevant registry fragments and deck regions, which controls KV-cache cost and improves instruction focus.

## Benchmark matrix

| Role | Candidate | Initial quantization | Decision question |
|---|---|---|---|
| Primary | Llama 4 Scout 17B-16E Instruct | Q4_K_M GGUF | Does MoE quality remain usable at acceptable CPU latency? |
| Quality control | Llama 3.3 70B Instruct | Q4_K_M GGUF | Does dense 70B materially improve BSAM tool/edit accuracy enough to justify latency? |
| Fast development | Llama 3.1 8B Instruct | Q6_K GGUF | Is it adequate for intent parsing and simple registry queries? |

Measure cold load, prompt processing, generation tokens/second, first-token latency, peak working set, schema-valid response rate, exact tool/argument accuracy, hallucinated-capability rate, and success on multi-record changes such as a two-ply to eight-ply section edit.

No model or runtime is installed by this decision. GGUF availability, conversion provenance, checksums, licensing, and the exact `llama.cpp` build must be pinned when the benchmark milestone begins.

## Official references

- [Meta Llama 4 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama4/MODEL_CARD.md)
- [Meta Llama 3.3 model card](https://github.com/meta-llama/llama-models/blob/main/models/llama3_3/MODEL_CARD.md)
- [Meta prompt formats and function calling](https://github.com/meta-llama/llama-models/blob/main/models/llama4/README.md)
- [`llama.cpp` repository and server](https://github.com/ggml-org/llama.cpp)
- [`llama.cpp` grammar and JSON-Schema constraints](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
