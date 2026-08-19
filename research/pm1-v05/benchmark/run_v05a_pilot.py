#!/usr/bin/env python3
"""V0.5 preflight pilot: horizons 10/50/100 x 2 conditions x 1 scenario x 1 trial.

Exact API-call count: (10 + 50 + 100) x 2 = 320 calls.

NOT RUN during implementation. Execute only after explicit user approval.

Verifies: token accounting, history growth, PM-1 boundedness, no prompt
leakage, both conditions solve the same task, per-hop persistence, replay.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.llm_runner import get_model_config
from lib.v05a_chain import (
    PILOT_HORIZONS,
    CONDITIONS,
    run_v05a_chain,
    aggregate_v05a_metrics,
    scaling_analysis,
    context_ceiling_analysis,
    generate_v05a_report,
    chain_result_to_dict,
    generate_chain_spec_at_horizon,
)
from lib.v05a_worker import LLMV05Worker

RESULTS_DIR = Path(_PROJECT_ROOT) / "results" / "v0.5"


def main() -> int:
    results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)

    model_config = get_model_config()
    pilot_calls = sum(PILOT_HORIZONS) * len(CONDITIONS)
    print(f"[v05a-pilot] horizons={PILOT_HORIZONS} conditions={CONDITIONS} "
          f"=> {pilot_calls} API calls", file=sys.stderr)

    p_results: list[Any] = []
    c_results: list[Any] = []
    all_hop_records: list[dict[str, Any]] = []

    start = time.time()
    for horizon in PILOT_HORIZONS:
        spec = generate_chain_spec_at_horizon(1, horizon, chain_count=10)
        for condition in CONDITIONS:
            worker = LLMV05Worker(model_config)
            result = run_v05a_chain(spec, condition, worker)
            all_hop_records.extend(chain_result_to_dict(result)["hop_records"])
            (p_results if condition == "P" else c_results).append(result)
            print(f"[v05a-pilot] h={horizon} {condition}: survived={result.chain_survived} "
                  f"fails={result.total_failures} cum_tok={result.cumulative_tokens} "
                  f"max_ctx={result.max_transmitted_tokens}", file=sys.stderr)

    elapsed = time.time() - start
    print(f"[v05a-pilot] completed in {elapsed:.0f}s", file=sys.stderr)

    report = generate_v05a_report(p_results, c_results)
    (results_dir / "V0.5_PILOT_REPORT.md").write_text(report, encoding="utf-8")

    raw: dict[str, Any] = {
        "pilot_calls": pilot_calls,
        "conditions": CONDITIONS,
        "horizons": PILOT_HORIZONS,
        "p_metrics": aggregate_v05a_metrics(p_results),
        "c_metrics": aggregate_v05a_metrics(c_results),
        "scaling": scaling_analysis(p_results, c_results),
        "context_ceiling": context_ceiling_analysis(p_results + c_results),
        "p_chains": [chain_result_to_dict(r) for r in p_results],
        "c_chains": [chain_result_to_dict(r) for r in c_results],
    }
    (results_dir / "v05a_pilot_results.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    (results_dir / "v05a_pilot_hop_records.json").write_text(
        json.dumps(all_hop_records, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[v05a-pilot] artifacts written to {results_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
