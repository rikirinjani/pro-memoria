#!/usr/bin/env python3
"""V0.5a full experiment — checkpointed executor (execution infrastructure only).

Uses the IDENTICAL registered configuration and lib.v05a_chain functions:
  - HORIZONS [10, 25, 50, 100, 250, 500, 1000]
  - CONDITIONS P, C
  - 10 scenarios x 3 trials
  - 116,100 API calls (verified at startup)

Why this executor: the registered runner (run_v05a_full.py) persists only at
the very end. At ~1.3 s/call this run takes ~40 hours; any interruption would
lose all results. This executor calls the same lib functions with the same
parameters but persists per-horizon hop records + a checkpoint manifest after
every horizon, and skips already-completed horizons on resume. NO experimental
parameter is changed.
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
CHECKPOINT = RESULTS_DIR / "v05a_full_checkpoint.json"
HOP_RECORDS_FILE = RESULTS_DIR / "v05a_full_hop_records.json"


def expected_calls() -> int:
    return sum(HORIZONS) * len(CONDITIONS) * SCENARIOS * TRIALS


def load_checkpoint() -> dict[str, Any]:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {"completed_horizons": [], "hop_records": []}


def save_checkpoint(cp: dict[str, Any]) -> None:
    CHECKPOINT.write_text(json.dumps(cp, indent=2, sort_keys=True), encoding="utf-8")
    HOP_RECORDS_FILE.write_text(
        json.dumps(cp["hop_records"], indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    total = expected_calls()
    print(f"[v05a-full-cp] total planned: {total} API calls "
          f"(horizons={HORIZONS} x cond={len(CONDITIONS)} x scen={SCENARIOS} x trials={TRIALS})",
          file=sys.stderr)
    assert total == 116100, f"registered call count mismatch: {total}"

    model_config = get_model_config()
    cp = load_checkpoint()
    done = set(cp["completed_horizons"])
    p_results: list[Any] = []
    c_results: list[Any] = []
    hop_records: list[dict[str, Any]] = list(cp["hop_records"])

    start_all = time.time()
    for horizon in HORIZONS:
        if horizon in done:
            print(f"[v05a-full-cp] horizon {horizon} already completed; skipping", file=sys.stderr)
            continue
        h_start = time.time()
        for scenario in range(1, SCENARIOS + 1):
            spec = generate_chain_spec_at_horizon(scenario, horizon, chain_count=SCENARIOS)
            for trial in range(1, TRIALS + 1):
                for condition in CONDITIONS:
                    worker = LLMV05Worker(model_config)
                    result = run_v05a_chain(spec, condition, worker)
                    hop_records.extend(chain_result_to_dict(result)["hop_records"])
                    (p_results if condition == "P" else c_results).append(result)
        h_elapsed = time.time() - h_start
        cp["completed_horizons"].append(horizon)
        cp["hop_records"] = hop_records
        save_checkpoint(cp)
        print(f"[v05a-full-cp] horizon {horizon} done in {h_elapsed:.0f}s; "
              f"persisted {len(hop_records)} hop records", file=sys.stderr)

    # Rebuild results from checkpoint records (deterministic replay of stored data
    # is not needed for aggregation; reload from raw JSON is done in analysis).
    print(f"[v05a-full-cp] all horizons completed in {time.time() - start_all:.0f}s; "
          f"total persisted hop records: {len(hop_records)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
