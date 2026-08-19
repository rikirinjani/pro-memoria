#!/usr/bin/env python3
"""Run the V0.4a preflight pilot: 1 chain x 10 hops x 4 conditions = 40 API calls.

NOT RUN during implementation. Execute only after explicit user approval.

F4 (pilot observability): the pilot uses a multi-unit chain (chain-06,
initial position -3, target 1) so a +1/-1 corruption flip is NOT absorbed in
one step — corruption propagation is observable. This is an observability
improvement; the scientific hypothesis is unchanged.

F3 (per-hop persistence): all HopRecords are written to
results/v0.4a/revalidation/ as JSON (no secrets).

Usage:
    python run_v04a_pilot.py
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

from lib.v04a_generator import generate_single_chain_spec
from lib.v04a_chain import (
    run_chain,
    aggregate_metrics,
    first_failure_hops,
    generate_v04a_report,
    chain_result_to_dict,
)
from lib.v04a_worker import LLMHandoffWorker

CONDITIONS = ["H-full", "H-direct", "H-corrupt", "H-recover"]
# F4: multi-unit chain — initial position -3, target 1 (|pos - target| = 4)
PILOT_CHAIN_INDEX = 6
PILOT_HOPS = 10
RESULTS_DIR = Path(_PROJECT_ROOT) / "results" / "v0.4a" / "revalidation"


def main() -> int:
    results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)

    from lib.llm_runner import get_model_config
    model_config = get_model_config()

    print(f"[v04a-pilot] 1 chain x {PILOT_HOPS} hops x {len(CONDITIONS)} conditions "
          f"= {PILOT_HOPS * len(CONDITIONS)} API calls", file=sys.stderr)

    spec = generate_single_chain_spec(PILOT_CHAIN_INDEX, hops=PILOT_HOPS, chain_count=10)
    print(f"[v04a-pilot] chain={spec.chain_id} initial={spec.initial_state.position_qty},"
          f"target={spec.initial_state.target_signal} corrupt_hops={spec.corrupt_hops} "
          f"restore_hops={spec.restore_hops}", file=sys.stderr)

    experiment = {
        "chains": {},
        "chain_ids": [spec.chain_id],
        "conditions": CONDITIONS,
        "hops": PILOT_HOPS,
    }
    all_hop_records: list[dict[str, Any]] = []

    start = time.time()
    for condition in CONDITIONS:
        worker = LLMHandoffWorker(model_config)
        result = run_chain(spec, condition, worker)
        experiment["chains"][condition] = {spec.chain_id: result}
        # F3: persist per-hop records for every executed hop.
        all_hop_records.extend(chain_result_to_dict(result)["hop_records"])
        print(f"[v04a-pilot] {condition}: {result.chain_survived} survived, "
              f"{result.total_failures} failures, first fail hop={result.first_failed_hop}",
              file=sys.stderr)

    elapsed = time.time() - start
    print(f"[v04a-pilot] completed in {elapsed:.0f}s", file=sys.stderr)

    # Reports + raw artifacts (isolated under revalidation/)
    report = generate_v04a_report(experiment)
    (results_dir / "V0.4a_REVALIDATION_PILOT_REPORT.md").write_text(report, encoding="utf-8")

    raw: dict[str, Any] = {"experiment": {}}
    for condition in CONDITIONS:
        chain_results = list(experiment["chains"][condition].values())
        metrics = aggregate_metrics(chain_results)
        raw["experiment"][condition] = {
            "metrics": metrics,
            "chains": first_failure_hops(chain_results),
        }
    (results_dir / "v04a_revalidation_pilot_results.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

    # F3: full per-hop persistence (deterministic, replayable, no secrets).
    (results_dir / "v04a_revalidation_hop_records.json").write_text(
        json.dumps(all_hop_records, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[v04a-pilot] artifacts written to {results_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
