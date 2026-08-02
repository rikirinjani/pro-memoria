"""PM-1 Pipeline: benchmark first, then evaluate with Bonsai.

Runs:
  1. loop_bench.py --runs N     (fast benchmark, token efficiency)
  2. loop_eval.py --count M     (Bonsai critique on crucible traces)

Output:
  bench/results/pipeline_{timestamp}/
    bench/           — benchmark aggregate + per-run
    eval/            — evaluation results
    pipeline.json    — combined summary
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))

from bench.loop_bench import run_all as run_bench
from bench.loop_eval import run_all as run_eval

OUTPUT_DIR = HERE / "results"
N_BENCH = 100
N_EVAL = 5

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def main(bench_runs: int, eval_count: int):
    ts = now_iso().replace(":", "-").split(".")[0]
    pipeline_dir = OUTPUT_DIR / f"pipeline_{ts}"
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("PM-1 Pipeline Run")
    print(f"  Started:  {now_iso()}")
    print(f"  Benchmark: {bench_runs} runs")
    print(f"  Eval:      {eval_count} traces")
    print(f"  Output:    {pipeline_dir}")
    print("=" * 60)
    print()

    # ── Phase 1: Benchmark ────────────────────────────────────
    print(">>> PHASE 1: Benchmark Loop")
    print(f">>> {bench_runs} runs (est. {bench_runs * 0.5:.0f}s = {bench_runs * 0.5 / 60:.1f} min)")
    print()

    t0 = time.time()
    # Override OUTPUT_DIR for bench to go into pipeline subdir
    import bench.loop_bench as lb
    lb.OUTPUT_DIR = pipeline_dir / "bench"

    bench_result = run_bench(bench_runs)
    bench_dur = time.time() - t0

    print()
    print(f">>> Benchmark complete in {bench_dur:.0f}s")
    if bench_result.get("avg_savings_pct") is not None:
        print(f">>> Avg savings: {bench_result['avg_savings_pct']}% "
              f"(range {bench_result['min_savings_pct']}% - {bench_result['max_savings_pct']}%)")
    print()

    # ── Phase 2: Evaluation ────────────────────────────────────
    print(">>> PHASE 2: Self-Evaluation Loop (Bonsai 27B)")
    print(f">>> {eval_count} traces (est. {eval_count * 200:.0f}s = {eval_count * 200 / 60:.1f} min)")
    print()

    t0 = time.time()
    # Override OUTPUT_DIR for eval
    import bench.loop_eval as le
    le.OUTPUT_DIR = pipeline_dir / "eval"

    eval_result = run_eval(eval_count)
    eval_dur = time.time() - t0

    print()
    print(f">>> Eval complete in {eval_dur:.0f}s")
    if eval_result.get("avg_score") is not None:
        print(f">>> Avg score: {eval_result['avg_score']}/10 "
              f"(range {eval_result['min_score']} - {eval_result['max_score']})")
        print(f">>> Plausible: {eval_result['plausible_pct']}%")
    print()

    # ── Summary ────────────────────────────────────────────────
    pipeline_result = {
        "timestamp": ts,
        "duration_s": {
            "benchmark": round(bench_dur, 1),
            "eval": round(eval_dur, 1),
            "total": round(bench_dur + eval_dur, 1),
        },
        "benchmark": {k: v for k, v in bench_result.items() if k != "runs"},
        "evaluation": {k: v for k, v in eval_result.items() if k != "results"},
    }

    pipeline_path = pipeline_dir / "pipeline.json"
    with open(pipeline_path, "w") as f:
        json.dump(pipeline_result, f, indent=2)

    print("=" * 60)
    print("PIPELINE COMPLETE")
    print(f"  Total time: {pipeline_result['duration_s']['total']:.0f}s")
    if bench_result.get("avg_savings_pct") is not None:
        print(f"  Benchmark:  {bench_result['avg_savings_pct']}% avg savings")
    if eval_result.get("avg_score") is not None:
        print(f"  Eval:       {eval_result['avg_score']}/10 avg score")
    print(f"  Results:    {pipeline_dir}")
    print("=" * 60)

    return pipeline_result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PM-1 Pipeline (bench + eval)")
    parser.add_argument("--bench-runs", type=int, default=N_BENCH,
                        help="Benchmark iterations (default: 100)")
    parser.add_argument("--eval-count", type=int, default=N_EVAL,
                        help="Traces for Bonsai eval (default: 5)")
    args = parser.parse_args()
    main(args.bench_runs, args.eval_count)
