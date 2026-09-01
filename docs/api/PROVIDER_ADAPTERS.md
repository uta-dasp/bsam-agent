# Model-provider adapters

Model assistance is optional. The deterministic core and Agent API do not depend on a particular vendor, SDK, or model.

## Model-acquisition gate

No model runtime or weights are required while G0-G3 are being implemented. Acquire the first Meta model only at roadmap item G4.3, after the deterministic vertical slice, strict Agent tool schemas, policy enforcement, and checked-in synthetic evaluations exist. This prevents model choice from defining BSAM correctness and provides an objective benchmark before committing disk space and setup time.

The user must accept the applicable Meta license. Model weights are stored outside this repository and ignored by Git; configuration refers to a local path and verified checksum. The runtime must bind to loopback only and must not fetch models or send telemetry during normal operation.

## Common application contract

Each adapter receives:

- a bounded list of messages;
- a strict response JSON Schema or tool definitions;
- provider-independent generation limits;
- a data-policy classification;
- a request correlation identifier.

Each adapter returns structured content, validated tool calls, or a normalized provider error. Vendor response objects are not exposed through the BSAM Agent API.

## Initial provider paths

| Path | Transport | Intended use | Groundwork decision |
|---|---|---|---|
| CPU-local | Local loopback HTTP API | Real local project assistance after G4.2 and benchmarking | Preferred for private data; choose the smallest evaluated model that passes the acceptance thresholds |
| Gemini | Native Gemini API | Free experimentation with synthetic/sanitized cases, later paid use | Adapter planned; free tier excluded for real BSAM/project data |
| OpenAI | Responses API | Later paid structured output and tool calling | Adapter planned; explicit storage/data controls required |

Chinese-origin model families are outside the project allowlist.

## CPU-local evaluation

The local adapter should not be tied to one runtime until a benchmark is complete. Candidate runtimes must provide a loopback API, constrained JSON or tool calling, bounded context configuration, deterministic-enough test settings, and usable Windows CPU performance.

The initial Meta-focused matrix is defined in [Local model recommendation](LOCAL_MODEL_RECOMMENDATION.md). Treat named candidates as benchmark hypotheses, subject to license, format, runtime support, and measured performance at G4.3. Measure:

- valid-schema rate without repair;
- correct tool selection and argument accuracy;
- refusal to invent unsupported BSAM capabilities;
- latency and tokens per second on representative bounded prompts;
- peak working memory;
- behavior when the capability registry returns an unknown or ambiguity.

The 512 GiB system can hold large quantized weights, but the two Broadwell-era CPUs make response latency the practical selection constraint. Start small for interaction and consider a larger batch model only if evaluation shows a material accuracy benefit.

## Gemini adapter

Use native structured output for typed intent and function calling for Agent tools. Do not ask a model to produce the final `.in` text. The adapter validates the response locally before returning it.

Official references:

- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling)
- [Gemini API pricing and data-use tiers](https://ai.google.dev/gemini-api/docs/pricing)

## OpenAI adapter

Use the Responses API with strict structured output/function schemas. Set data-storage behavior explicitly in configuration and keep payload minimization independent of provider retention promises.

Official references:

- [OpenAI Responses create API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
- [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)

## Configuration boundary

Provider settings are local configuration, not model data. The planned configuration schema contains provider identifier, model identifier, endpoint, credential reference, timeout, maximum output, and data-policy mode. It never contains an API key value.

No provider is enabled by default, and switching providers cannot change the BSAM capability registry, validation rules, renderer, or run policy.
