"""PM-1 Benchmark Loop — runs on Mac Mini independently.

Reuses existing benchmark infrastructure (token_efficiency.py crucible)
and extends it with:
  - Multi-run support (N iterations for statistical significance)
  - Results aggregation across runs
  - Comparison against previous runs

Designed to run independently on Mac Mini; Windows can be off.

Usage:
    source venv/bin/activate
    python bench/loop_bench.py [--runs N] [--quick]

Output:
    bench/results/bench_{timestamp}/
        run_{i}/                 — per-run results
        aggregate.json            — aggregated across all runs
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))

from bench.token_efficiency import run_crucible_benchmark

OUTPUT_DIR = HERE / "results"
N_RUNS = 3          # default number of iterations

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def run_all(runs: int):
    """Run N benchmark iterations, aggregate results."""
    timestamp = now_iso().replace(":", "-").split(".")[0]
    run_dir = OUTPUT_DIR / f"bench_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"PM-1 Benchmark Loop")
    print(f"  Runs:     {runs}")
    print(f"  Mode:     full")
    print(f"  Output:   {run_dir}")
    print()
    
    all_runs = []
    
    for i in range(runs):
        print(f"[{i+1}/{runs}] Benchmark run {i+1}...")
        start = time.time()
        
        try:
            result = run_crucible_benchmark()
            duration = time.time() - start
            result["run_duration_s"] = round(duration, 1)
            result["run_index"] = i
            result["timestamp"] = now_iso()
            
            # Save per-run
            run_path = run_dir / f"run_{i:03d}.json"
            with open(run_path, "w") as f:
                json.dump(result, f, indent=2)
            
            # morse_vs_steelman_pct inside cl100k_base tokenizer results
            tok_results = result.get("cl100k_base", {})
            savings = tok_results.get("morse_vs_steelman_pct", "?")
            print(f"  Duration: {duration:.1f}s | Morse vs Steelman: {savings}%")
            
            all_runs.append(result)
            
        except Exception as e:
            print(f"  FAILED: {e}")
            all_runs.append({"run_index": i, "error": str(e), "timestamp": now_iso()})
        
        if i < runs - 1:
            time.sleep(1)
    
    # Aggregate
    valid_runs = [r for r in all_runs if "error" not in r]
    
    if valid_runs:
        savings_vals = []
        for r in valid_runs:
                tok_r = r.get("cl100k_base", {})
                sv = tok_r.get("morse_vs_steelman_pct")
                if isinstance(sv, (int, float)):
                    savings_vals.append(sv)
        
        aggregate = {
            "timestamp": timestamp,
            "n_runs": runs,
            "n_valid": len(valid_runs),
            "mode": "full",
            "avg_savings_pct": round(sum(savings_vals) / len(savings_vals), 1) if savings_vals else None,
            "min_savings_pct": min(savings_vals) if savings_vals else None,
            "max_savings_pct": max(savings_vals) if savings_vals else None,
            "avg_duration_s": round(sum(r.get("run_duration_s", 0) for r in valid_runs) / len(valid_runs), 1),
            "runs": all_runs,
        }
    else:
        aggregate = {
            "timestamp": timestamp,
            "n_runs": runs,
            "n_valid": 0,
            "error": "All runs failed",
            "runs": all_runs,
        }
    
    agg_path = run_dir / "aggregate.json"
    with open(agg_path, "w") as f:
        json.dump(aggregate, f, indent=2)
    
    print()
    print(f"Done. Results in: {run_dir}")
    if aggregate.get("avg_savings_pct") is not None:
        print(f"  Runs:        {runs} ({aggregate['n_valid']} valid)")
        print(f"  Avg savings: {aggregate['avg_savings_pct']}%")
        print(f"  Range:       {aggregate['min_savings_pct']}% – {aggregate['max_savings_pct']}%")
        print(f"  Avg dur:     {aggregate['avg_duration_s']}s")
    else:
        for r in all_runs:
            if "error" in r:
                print(f"  Run {r['run_index']}: {r['error']}")
    
    return aggregate

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PM-1 Benchmark Loop")
    parser.add_argument("--runs", type=int, default=N_RUNS, help="Number of benchmark iterations")
    parser.add_argument("--quick", action="store_true", help="(unused)")
    args = parser.parse_args()
    
    run_all(args.runs)
