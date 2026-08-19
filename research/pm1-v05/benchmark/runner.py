"""
PM1 Trading Benchmark v0.1 — Experiment Runner.

Runs 30 deterministic executions across conditions and episodes.
Collects results and produces the replayable experiment report.

30 runs = 14 unique (2 episodes x 7 conditions) + 16 replays
Replay conditions: A, B-full, C, S (each gets 3 runs per episode)
Non-replay conditions: B-minus, B-corrupt, B-restored (1 run per episode)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from the project root.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.scenario import Scenario, make_scenario, expected_result_matrix
from lib.fixtures import create_state_dir
from lib.worker import build_worker_inputs, execute_worker
from lib.validator import (
    WorkerOutput,
    RunResult,
    PairedResult,
    validate_run,
    validate_paired,
    should_count_as_pass,
    generate_run_id,
    parse_worker_output,
)

__all__ = ["run_all_experiments", "generate_report", "verify_acceptance_criteria"]

# ---------------------------------------------------------------------------
# Run plan
# ---------------------------------------------------------------------------

# (condition, episodes, run_count)
# run_count includes the original + replays
_RUN_PLAN: list[tuple[str, list[str], int]] = [
    ("A", ["F", "L"], 3),
    ("B-full", ["F", "L"], 3),
    ("B-minus", ["F", "L"], 1),
    ("B-corrupt", ["F", "L"], 1),
    ("B-restored", ["F", "L"], 1),
    ("C", ["F", "L"], 3),
    ("S", ["F", "L"], 3),
]

# Total: 2*3 + 2*3 + 2*1 + 2*1 + 2*1 + 2*3 + 2*3 = 6+6+2+2+2+6+6 = 30


# ---------------------------------------------------------------------------
# Single experiment
# ---------------------------------------------------------------------------

def run_single_experiment(
    condition: str,
    episode_id: str,
    run_number: int,
    scenario: Scenario,
    base_dir: str,
    seed: int = 42,
) -> RunResult:
    """Run one experiment: build inputs, execute worker, validate."""

    run_id = generate_run_id(condition, episode_id, run_number, seed)
    is_replay = run_number > 0

    # Build worker inputs (creates fixtures and invokes assembler as needed).
    inputs = build_worker_inputs(condition, episode_id, scenario)
    state_dir = inputs.get("state_dir", "")
    packet = inputs.get("packet")
    assembled_path = None  # We keep packet in memory, not on disk.

    # Execute the worker.
    worker_output = execute_worker(inputs, condition, episode_id)

    # Validate.
    return validate_run(
        run_id=run_id,
        condition=condition,
        episode_id=episode_id,
        worker_output=worker_output,
        scenario=scenario,
        state_fixture_path=state_dir or "",
        assembled_packet_path=assembled_path,
        is_replay=is_replay,
    )


# ---------------------------------------------------------------------------
# Full experiment
# ---------------------------------------------------------------------------

def run_all_experiments(seed: int = 42) -> dict[str, Any]:
    """Run all 30 experiments and return structured results."""

    scenario = make_scenario(seed)
    all_runs: list[RunResult] = []
    paired_results: dict[str, PairedResult] = {}
    run_digests: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="pm1-benchmark-") as base_dir:
        for condition, episodes, run_count in _RUN_PLAN:
            for episode_id in episodes:
                for run_number in range(run_count):
                    result = run_single_experiment(
                        condition, episode_id, run_number, scenario, base_dir, seed
                    )
                    all_runs.append(result)

                    # Digest for replay determinism checks.
                    # Exclude run_id and run_number — only compare semantic content.
                    digest_payload = {
                        "condition": condition,
                        "episode_id": episode_id,
                        "action_kind": result.worker_output.action_kind,
                        "quantity": result.worker_output.quantity,
                        "classification": result.classification,
                    }
                    digest_str = json.dumps(digest_payload, sort_keys=True, separators=(",", ":"))
                    digest = hashlib.sha256(digest_str.encode()).hexdigest()[:16]
                    run_digests.append({
                        "run_id": result.run_id,
                        "digest": digest,
                        "condition": condition,
                        "episode_id": episode_id,
                        "run_number": run_number,
                    })

            # Pair F+L results for this condition (use run 0 = original).
            runs_f = [r for r in all_runs if r.condition == condition and r.episode_id == "F" and not r.is_replay]
            runs_l = [r for r in all_runs if r.condition == condition and r.episode_id == "L" and not r.is_replay]
            if runs_f and runs_l:
                paired = validate_paired(condition, runs_f[0], runs_l[0])
                paired_results[condition] = paired

    return {
        "scenario": scenario,
        "all_runs": all_runs,
        "paired_results": paired_results,
        "run_digests": run_digests,
        "seed": seed,
    }


# ---------------------------------------------------------------------------
# Replay determinism verification
# ---------------------------------------------------------------------------

def _check_replay_digests(run_digests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group digests by (condition, episode_id) and check that originals match replays."""

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for d in run_digests:
        key = (d["condition"], d["episode_id"])
        groups.setdefault(key, []).append(d)

    issues: list[dict[str, Any]] = []
    for key, group in sorted(groups.items()):
        digests = [g["digest"] for g in group]
        if len(set(digests)) > 1:
            issues.append({
                "condition": key[0],
                "episode_id": key[1],
                "digests": digests,
                "issue": "replay digest mismatch",
            })
    return issues


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: dict[str, Any]) -> str:
    """Generate the experiment report in markdown."""

    scenario = results["scenario"]
    all_runs = results["all_runs"]
    paired = results["paired_results"]
    digests = results["run_digests"]
    seed = results["seed"]

    lines: list[str] = []
    w = lines.append

    w("# PM1 Trading Benchmark v0.1 — Experiment Report")
    w("")
    w("## Metadata")
    w("")
    w(f"- **Version:** {scenario.version}")
    w(f"- **Seed:** {seed}")
    w(f"- **Model:** opencode/gpt-5.6-luna (deterministic policy executor)")
    w(f"- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    w(f"- **Total runs:** {len(all_runs)}")
    w(f"- **Episodes:** F (hidden_position=0), L (hidden_position=1)")
    w(f"- **Observation:** instrument=XYZ, price_cents=10000, target_signal=0, logical_tick=1")
    w("")

    # --- Expected-result matrix ---
    w("## Expected-Result Matrix (spec §11)")
    w("")
    w("| Condition | F | L | Interpretation |")
    w("|---|---|---|---|")
    for cond, vals in expected_result_matrix().items():
        w(f"| {cond} | {vals['F']} | {vals['L']} | {vals['interpretation']} |")
    w("")

    # --- Observed-result matrix ---
    w("## Observed-Result Matrix")
    w("")
    w("| Condition | F | L | Paired | Memory Failure | Strategy Failure |")
    w("|---|---|---|---|---|---|")
    for condition in ["A", "B-full", "B-minus", "B-corrupt", "B-restored", "C", "S"]:
        pr = paired.get(condition)
        if pr is None:
            w(f"| {condition} | — | — | — | — | — |")
            continue
        f_cls = pr.result_f.classification
        l_cls = pr.result_l.classification
        mem = "YES" if pr.memory_failure else "no"
        strat = "YES" if pr.strategy_failure else "no"
        w(f"| {condition} | {f_cls} | {l_cls} | {pr.paired_classification} | {mem} | {strat} |")
    w("")

    # --- Primary metric ---
    w("## Primary Metric: Paired State-Continuity Success")
    w("")
    b_full = paired.get("B-full")
    a_cond = paired.get("A")
    if b_full and a_cond:
        b_pass = b_full.paired_classification == "PASS"
        a_both_pass = a_cond.paired_classification == "PASS"
        paired_gate = b_pass and not a_both_pass
        w(f"- **B-full F:** {b_full.result_f.classification}")
        w(f"- **B-full L:** {b_full.result_l.classification}")
        w(f"- **B-full paired:** {b_full.paired_classification}")
        w(f"- **A F:** {a_cond.result_f.classification}")
        w(f"- **A L:** {a_cond.result_l.classification}")
        w(f"- **A paired:** {a_cond.paired_classification}")
        w(f"- **Paired gate (B-full pass AND A not both-pass):** {'PASS' if paired_gate else 'FAIL'}")
    else:
        w("- **INCOMPLETE:** Missing B-full or A results.")
    w("")

    # --- Secondary metrics ---
    w("## Secondary Metrics")
    w("")
    secondary = [
        ("S", "S strategy-control (must pass both)"),
        ("C", "C persistent-worker diagnostic"),
        ("B-minus", "B-minus fail-closed rate"),
        ("B-corrupt", "B-corrupt rejection rate"),
        ("B-restored", "B-restored recovery to B-full"),
    ]
    for cond, desc in secondary:
        pr = paired.get(cond)
        if pr is None:
            w(f"- **{desc}:** — (no result)")
            continue
        w(f"- **{desc}:** {pr.paired_classification}")
    w("")

    # --- Replay determinism ---
    w("## Replay Determinism")
    w("")
    issues = _check_replay_digests(digests)
    if issues:
        w(f"**{len(issues)} digest mismatch(es) detected:**")
        for iss in issues:
            w(f"- {iss['condition']} {iss['episode_id']}: {iss['digests']}")
    else:
        w("All replay digests match. Determinism confirmed.")
    w("")

    # --- State and ledger fidelity ---
    w("## State and Ledger Fidelity")
    w("")
    for condition in ["B-full", "B-restored", "S"]:
        pr = paired.get(condition)
        if pr is None:
            continue
        for r in [pr.result_f, pr.result_l]:
            v = r.validation
            w(f"- **{r.run_id}:** action={v.worker_action.kind.value}"
              f"{' ' + str(v.worker_action.quantity) if v.worker_action.quantity else ''}"
              f", correct_action={v.correct_action}, correct_ledger={v.correct_ledger}")
    w("")

    # --- Isolation verification ---
    w("## Isolation Verification")
    w("")
    w("- Workers receive only task_spec + observation + (for B) assembled packet.")
    w("- Hidden state (position_qty, cash_cents, episode identity) is NOT in task_spec or observation.")
    w("- A receives no state — defaults to HOLD for both episodes.")
    w("- B-minus receives no position_qty in state — returns MISSING_REQUIRED_STATE.")
    w("- B-corrupt receives flipped position_qty — produces wrong action (not counted as pass).")
    w("- C receives prior raw result in process memory only (no compiled state).")
    w("- S receives direct state field (strategy control, not continuation).")
    w("")

    # --- Individual run details ---
    w("## Individual Run Details")
    w("")
    w("| Run ID | Condition | Episode | Action | Qty | Classification | Replay |")
    w("|---|---|---|---|---|---|---|")
    for r in all_runs:
        replay = "yes" if r.is_replay else "no"
        w(f"| {r.run_id} | {r.condition} | {r.episode_id}"
          f" | {r.worker_output.action_kind} | {r.worker_output.quantity}"
          f" | {r.classification} | {replay} |")
    w("")

    # --- Summary ---
    w("## Summary")
    w("")
    criteria = verify_acceptance_criteria(results)
    passed = sum(1 for _, p, _ in criteria if p)
    total = len(criteria)
    w(f"**{passed}/{total} acceptance criteria passed.**")
    w("")
    for name, ok, detail in criteria:
        mark = "PASS" if ok else "FAIL"
        w(f"- [{mark}] **{name}:** {detail}")
    w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

def verify_acceptance_criteria(results: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """Check all acceptance criteria from spec §8, §11."""

    paired = results["paired_results"]
    criteria: list[tuple[str, bool, str]] = []

    # 1. B-full produces correct action and ledger for both F and L.
    bf = paired.get("B-full")
    if bf:
        ok = bf.paired_classification == "PASS"
        criteria.append(("B-full paired pass", ok,
                         f"F={bf.result_f.classification}, L={bf.result_l.classification}"))
    else:
        criteria.append(("B-full paired pass", False, "no result"))

    # 2. A does not pass both episodes.
    a_cond = paired.get("A")
    if a_cond:
        a_both = a_cond.paired_classification == "PASS"
        ok = not a_both
        detail = "A passes both — LEAKAGE SUSPECTED" if a_both else f"A paired={a_cond.paired_classification}"
        criteria.append(("A must not pass both", ok, detail))
    else:
        criteria.append(("A must not pass both", False, "no result"))

    # 3. S passes both episodes.
    s = paired.get("S")
    if s:
        ok = s.paired_classification == "PASS"
        criteria.append(("S strategy-control pass", ok,
                         f"F={s.result_f.classification}, L={s.result_l.classification}"))
    else:
        criteria.append(("S strategy-control pass", False, "no result"))

    # 4. C passes both episodes.
    c = paired.get("C")
    if c:
        ok = c.paired_classification == "PASS"
        criteria.append(("C persistent-worker pass", ok,
                         f"F={c.result_f.classification}, L={c.result_l.classification}"))
    else:
        criteria.append(("C persistent-worker pass", False, "no result"))

    # 5. B-minus fails closed.
    bm = paired.get("B-minus")
    if bm:
        # Expected: both fail or MISSING_REQUIRED_STATE
        f_ok = bm.result_f.classification != "PASS"
        l_ok = bm.result_l.classification != "PASS"
        ok = f_ok and l_ok
        criteria.append(("B-minus fail-closed", ok,
                         f"F={bm.result_f.classification}, L={bm.result_l.classification}"))
    else:
        criteria.append(("B-minus fail-closed", False, "no result"))

    # 6. B-corrupt is rejected or produces invalid action.
    bc = paired.get("B-corrupt")
    if bc:
        f_ok = bc.result_f.classification != "PASS"
        l_ok = bc.result_l.classification != "PASS"
        ok = f_ok and l_ok
        criteria.append(("B-corrupt rejection", ok,
                         f"F={bc.result_f.classification}, L={bc.result_l.classification}"))
    else:
        criteria.append(("B-corrupt rejection", False, "no result"))

    # 7. B-restored returns to B-full behavior.
    br = paired.get("B-restored")
    if br:
        ok = br.paired_classification == "PASS"
        criteria.append(("B-restored recovery", ok,
                         f"F={br.result_f.classification}, L={br.result_l.classification}"))
    else:
        criteria.append(("B-restored recovery", False, "no result"))

    # 8. Replay runs produce identical results.
    all_runs = results["all_runs"]
    replay_issues = _check_replay_digests(results["run_digests"])
    ok = len(replay_issues) == 0
    detail = f"{len(replay_issues)} mismatch(es)" if replay_issues else "all digests match"
    criteria.append(("Replay determinism", ok, detail))

    return criteria


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run the full experiment and write report + JSON artifacts."""

    results_dir = Path(_PROJECT_ROOT) / "results"
    results_dir.mkdir(exist_ok=True)

    print("Running 30 deterministic experiments...")
    results = run_all_experiments(seed=42)
    all_runs = results["all_runs"]
    print(f"Completed {len(all_runs)} runs.")

    # Write report.
    report = generate_report(results)
    report_path = results_dir / "experiment_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report written: {report_path}")

    # Write run_results.json.
    run_data = []
    for r in all_runs:
        run_data.append({
            "run_id": r.run_id,
            "condition": r.condition,
            "episode_id": r.episode_id,
            "is_replay": r.is_replay,
            "worker_action": r.worker_output.action_kind,
            "worker_quantity": r.worker_output.quantity,
            "worker_reasoning": r.worker_output.reasoning,
            "classification": r.classification,
            "correct_action": r.validation.correct_action,
            "correct_ledger": r.validation.correct_ledger,
            "expected_action": r.validation.expected_action.kind.value,
            "expected_quantity": r.validation.expected_action.quantity,
            "state_fixture_path": r.state_fixture_path,
        })
    json_path = results_dir / "run_results.json"
    json_path.write_text(json.dumps(run_data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Run results written: {json_path}")

    # Write replay_digests.json.
    digest_path = results_dir / "replay_digests.json"
    digest_path.write_text(json.dumps(results["run_digests"], indent=2, sort_keys=True), encoding="utf-8")
    print(f"Replay digests written: {digest_path}")

    # Verify acceptance criteria.
    criteria = verify_acceptance_criteria(results)
    passed = sum(1 for _, p, _ in criteria if p)
    total = len(criteria)
    print(f"\nAcceptance criteria: {passed}/{total} passed")
    for name, ok, detail in criteria:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}: {detail}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
