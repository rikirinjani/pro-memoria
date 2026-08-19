#!/usr/bin/env python3
"""Run the full V0.4a experiment: 10 chains x 100 hops x 4 conditions = 4,000 API calls.

NOT RUN during implementation. Execute only after explicit user approval.

Usage:
    python run_v04a_full.py
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

from lib.v04a_generator import generate_chain_specs, diversity_report
from lib.v04a_chain import (
    run_chain,
    aggregate_metrics,
    first_failure_hops,
    generate_v04a_report,
    chain_result_to_dict,
)
from lib.v04a_worker import LLMHandoffWorker

CONDITIONS = ["H-full", "H-direct", "H-corrupt", "H-recover"]
CHAIN_COUNT = 10
HOPS = 100
# Full experiment outputs go to a NEW dedicated results location
# (results/v0.4a/full/), NOT the revalidation directory. Prior artifacts
# (V0.1-V0.3a, V0.4a pilot, V0.4a revalidation) are preserved untouched.
RESULTS_DIR = Path(_PROJECT_ROOT) / "results" / "v0.4a" / "full"


def main() -> int:
    results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)

    from lib.llm_runner import get_model_config
    model_config = get_model_config()

    print(f"[v04a-full] {CHAIN_COUNT} chains x {HOPS} hops x {len(CONDITIONS)} conditions "
          f"= {CHAIN_COUNT * HOPS * len(CONDITIONS)} API calls", file=sys.stderr)

    specs = generate_chain_specs(chains=CHAIN_COUNT, hops=HOPS)
    print(f"[v04a-full] diversity: {diversity_report(specs)}", file=sys.stderr)

    experiment = {
        "chains": {},
        "chain_ids": [s.chain_id for s in specs],
        "conditions": CONDITIONS,
        "hops": HOPS,
    }
    all_hop_records: list[dict[str, Any]] = []

    start = time.time()
    for condition in CONDITIONS:
        experiment["chains"][condition] = {}
        for spec in specs:
            worker = LLMHandoffWorker(model_config)
            result = run_chain(spec, condition, worker)
            experiment["chains"][condition][spec.chain_id] = result
            # F3: persist per-hop records for every executed hop.
            all_hop_records.extend(chain_result_to_dict(result)["hop_records"])
        chain_results = list(experiment["chains"][condition].values())
        metrics = aggregate_metrics(chain_results)
        print(f"[v04a-full] {condition}: survival={metrics['chain_survival_rate']:.1%}, "
              f"handoff={metrics['handoff_success_rate']:.1%}", file=sys.stderr)

    elapsed = time.time() - start
    print(f"[v04a-full] completed in {elapsed:.0f}s", file=sys.stderr)

    # Reports + raw artifacts (isolated under results/v0.4a/full/)
    report = generate_v04a_report(experiment)
    (results_dir / "V0.4a_FULL_REPORT.md").write_text(report, encoding="utf-8")

    raw: dict[str, Any] = {"experiment": {}}
    for condition in CONDITIONS:
        chain_results = list(experiment["chains"][condition].values())
        raw["experiment"][condition] = {
            "metrics": aggregate_metrics(chain_results),
            "chains": first_failure_hops(chain_results),
        }
    raw["diversity"] = diversity_report(specs)
    (results_dir / "v04a_full_results.json").write_text(
        json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

    # F3: full per-hop persistence (deterministic, replayable, no secrets).
    (results_dir / "v04a_full_hop_records.json").write_text(
        json.dumps(all_hop_records, indent=2, sort_keys=True), encoding="utf-8")

    print(f"[v04a-full] artifacts written to {results_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
