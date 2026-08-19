#!/usr/bin/env python3
"""V0.5 full experiment: 7 horizons x 2 conditions x 10 scenarios x 3 trials.

Exact API-call count:
    sum(HORIZONS) x CONDITIONS x SCENARIOS x TRIALS
  = 1935 x 2 x 10 x 3
  = 116,100 calls

NOT RUN. Execute only after explicit user approval.
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
    HORIZONS,
    CONDITIONS,
    run_v05a_chain,
    aggregate_v05a_metrics,
    scaling_analysis,
    context_ceiling_analysis,
    relative_efficiency,
    generate_v05a_report,
    chain_result_to_dict,
    generate_chain_spec_at_horizon,
)
from lib.v05a_worker import LLMV05Worker

RESULTS_DIR = Path(_PROJECT_ROOT) / "results" / "v0.5"
SCENARIOS = 10
TRIALS = 3


def main() -> int:
    results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)

    model_config = get_model_config()
    full_calls = sum(HORIZONS) * len(CONDITIONS) * SCENARIOS * TRIALS
    print(f"[v05a-full] horizons={HORIZONS} conditions={CONDITIONS} "
          f"scenarios={SCENARIOS} trials={TRIALS} => {full_calls} API calls",
          file=sys.stderr)

    p_results: list[Any] = []
    c_results: list[Any] = []
    all_hop_records: list[dict[str, Any]] = []

    start = time.time()
    for horizon in HORIZONS:
        for scenario in range(1, SCENARIOS + 1):
            spec = generate_chain_spec_at_horizon(scenario, horizon, chain_count=SCENARIOS)
            for trial in range(1, TRIALS + 1):
                for condition in CONDITIONS:
                    worker = LLMV05Worker(model_config)
                    result = run_v05a_chain(spec, condition, worker)
                    all_hop_records.extend(chain_result_to_dict(result)["hop_records"])
                    (p_results if condition == "P" else c_results).append(result)
        mp = aggregate_v05a_metrics([r for r in p_results if r.horizon == horizon])
        mc = aggregate_v05a_metrics([r for r in c_results if r.horizon == horizon])
        print(f"[v05a-full] h={horizon}: P surv={mp['chain_survival_rate']:.1%} "
              f"tok={mp['cumulative_tokens']} | C surv={mc['chain_survival_rate']:.1%} "
              f"tok={mc['cumulative_tokens']}", file=sys.stderr)

    elapsed = time.time() - start
    print(f"[v05a-full] completed in {elapsed:.0f}s", file=sys.stderr)

    report = generate_v05a_report(p_results, c_results)
    (results_dir / "V0.5_FULL_REPORT.md").write_text(report, encoding="utf-8")

    raw: dict[str, Any] = {
        "full_calls": full_calls,
        "conditions": CONDITIONS,
        "horizons": HORIZONS,
        "scenarios": SCENARIOS,
        "trials": TRIALS,
        "p_metrics": aggregate_v05a_metrics(p_results),
        "c_metrics": aggregate_v05a_metrics(c_results),
        "scaling": scaling_analysis(p_results, c_results),
        "context_ceiling": context_ceiling_analysis(p_results + c_results),
        "relative_efficiency": relative_efficiency(p_results, c_results),
        "p_chains": [chain_result_to_dict(r) for r in p_results],
        "c_chains": [chain_result_to_dict(r) for r in c_results],
    }
    (results_dir / "v05a_full_results.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")
    (results_dir / "v05a_full_hop_records.json").write_text(
        json.dumps(all_hop_records, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[v05a-full] artifacts written to {results_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
