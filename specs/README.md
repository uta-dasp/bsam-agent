# BSAM specification registry

The curated registry is the machine-readable source for the generated BSAM input API reference. It stores behavior descriptions and local evidence locators, never copied BSAM implementation text.

## Commands

From the repository root:

```powershell
python tools/registry_tools.py validate
python tools/registry_tools.py generate
python tools/registry_tools.py check
```

`validate` checks repository-specific invariants with the Python standard library. The JSON Schema at `schemas/capability-registry.schema.json` documents the full data contract and will also be applied by a standards-compliant validator once development dependencies are introduced.

`generate` is the only supported way to update the generated Markdown reference. `check` fails when that reference is stale.
