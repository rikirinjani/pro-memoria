#!/usr/bin/env python3
"""V0.5a Checkpoint 1 executor — runs ONLY horizon 250 (15,000 calls), then stops.

Execution infrastructure only. Replicates the registered executor's per-horizon
loop EXACTLY (same lib.v05a_chain functions, same scenario->trial->condition
ordering, same LLMV05Worker, same checkpoint + hop-records files) but is
bounded to horizon 250 so it does NOT proceed to horizons 500/1000.

Does not restart from the beginning; skips already-completed horizons; appends
to the existing checkpoint; preserves all existing records.
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
    CONDITIONS,
    run_v05a_chain,
    chain_result_to_dict,
    generate_chain_spec_at_horizon,
)
from lib.v05a_worker import LLMV05Worker

RESULTS_DIR = Path(_PROJECT_ROOT) / "results" / "v0.5"
HORIZON = 250
SCENARIOS = 10
TRIALS = 3
CHECKPOINT = RESULTS_DIR / "v05a_full_checkpoint.json"
HOP_RECORDS_FILE = RESULTS_DIR / "v05a_full_hop_records.json"


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
    cp = load_checkpoint()

    calls = HORIZON * len(CONDITIONS) * SCENARIOS * TRIALS
    print(f"[v05a-cp1] planned calls for horizon {HORIZON}: {calls} (15,000)", file=sys.stderr)
    assert calls == 15000

    if HORIZON in cp["completed_horizons"]:
        print(f"[v05a-cp1] horizon {HORIZON} already completed; nothing to do", file=sys.stderr)
        return 0
    if not all(h in cp["completed_horizons"] for h in [10, 25, 50, 100]):
        print("[v05a-cp1] ERROR: prerequisite horizons 10/25/50/100 not all complete", file=sys.stderr)
        return 2

    model_config = get_model_config()
    hop_records: list[dict[str, Any]] = list(cp["hop_records"])
    start = time.time()
    made = 0

    for scenario in range(1, SCENARIOS + 1):
        spec = generate_chain_spec_at_horizon(scenario, HORIZON, chain_count=SCENARIOS)
        for trial in range(1, TRIALS + 1):
            for condition in CONDITIONS:
                worker = LLMV05Worker(model_config)
                result = run_v05a_chain(spec, condition, worker)
                hop_records.extend(chain_result_to_dict(result)["hop_records"])
                made += HORIZON
        print(f"[v05a-cp1] scenario {scenario}/10 done; total calls made so far this checkpoint: {made}",
              file=sys.stderr)

    elapsed = time.time() - start
    cp["completed_horizons"].append(HORIZON)
    cp["hop_records"] = hop_records
    save_checkpoint(cp)

    print(f"[v05a-cp1] horizon {HORIZON} COMPLETE in {elapsed:.0f}s; "
          f"calls made={made}; total persisted={len(hop_records)}", file=sys.stderr)
    print(f"[v05a-cp1] checkpoint updated: completed horizons = {cp['completed_horizons']}", file=sys.stderr)
    print(f"[v05a-cp1] STOPPING after checkpoint 1 (horizon 500 not started)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
