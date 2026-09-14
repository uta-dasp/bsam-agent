# VS Code and OpenAI routing acceptance — 2026-09-14

## Scope and privacy boundary

This acceptance exercised the installed VS Code chat client, the optional OpenAI
Responses routing adapter with `store: false`, and the deterministic local API on
the trusted `projects/notch_v1/notch_v1.in` deck. Only user-authored routing text,
bounded tool schemas, and prior routing decisions were eligible for the hosted
request. BSAM source bytes, parsed model data, deterministic tool results,
registry catalogs, API credentials, and audit contents remained local. No API key
or raw hosted payload is retained in this record.

## Observed workflow

The VS Code chat process connected to the configured `D:\Partha\BSAM` workspace.
The installed client then completed these deterministic operations:

- listed 28 available deterministic tool contracts;
- inspected the real notch deck through a workspace-relative path, finding two
  clusters, 10,444 nodes, 5,004 elements, zero errors, one compatibility warning,
  and 68,763 resolved references with no reference failures;
- previewed the exact registered `BOUNDARY.*CONVERGENCE[1].d_reduction` change
  from `0.25` to `0.5`, stopped at the confirmation boundary, and applied it only
  after a separate `/confirm` turn;
- rejected a request to invent unsupported BSAM syntax.

The original 1,855,192-byte deck remained byte-identical with SHA-256
`B7ACAA7EFEF23D27F9ADCD01FE24AD6D2BC2F5EC9CB997AEE221CC562DB9010D`.
The confirmed operation created a separate 1,855,191-byte deck with SHA-256
`626E06D6A186A344EFD64DBC6E7F65F80B2A8DB7839758AD62D8FED78FBB7100`
and a digest-bound audit sidecar. Post-apply validation reported zero errors, the
same one compatibility warning, and all 68,763 references resolved.

## Defects found and closed

The real workflow exposed three client defects: an unquoted absolute Windows path
lost its drive prefix, the natural-language editable-parameter question lacked a
deterministic query route, and an occupied default output or audit path caused a
late apply failure. Commit `5e2a5e9` closes all three with workspace-bound path
normalization, a conservative registry-backed editable-parameter listing, and
fresh numbered default output pairs. Focused tests cover each regression.

The initial hosted smoke request also exposed an invalid Responses structured-text
configuration and returned HTTP 400. Commit `54f8723` corrected the request
contract while retaining `store: false`, bounded HTTP errors, and local response
validation. A subsequent live non-sensitive `Hello` request completed normally.

## Qualification boundary

This evidence qualifies the installed-client inspect, capability, preview,
confirmation, apply, refusal, and optional hosted-routing paths exercised above.
It does not claim that arbitrary natural-language requests route correctly, permit
BSAM content in hosted requests, or weaken any deterministic validation or
confirmation boundary.
