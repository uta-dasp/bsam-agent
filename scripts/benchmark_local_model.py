"""Run the checked-in synthetic chat suite against a configured local provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bsam_agent.local_provider import LlamaCppProvider  # noqa: E402
from bsam_agent.model_benchmark import run_chat_benchmark  # noqa: E402
from bsam_agent.provider import load_provider_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=ROOT / "evals" / "chat_cases.json")
    parser.add_argument("--acceptance", type=Path, default=ROOT / "evals" / "acceptance.json")
    parser.add_argument("--peak-working-memory-gib", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_chat_benchmark(
        LlamaCppProvider(load_provider_config(args.config)),
        args.cases,
        args.acceptance,
        peak_working_memory_gib=args.peak_working_memory_gib,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
