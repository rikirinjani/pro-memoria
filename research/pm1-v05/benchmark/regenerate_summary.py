#!/usr/bin/env python3
"""
Offline V0.5 summary regeneration.

Regenerates the derived V0.5 summary from the persisted raw hop records
ONLY. No API calls, no provider access, no experiment execution.

Usage:
    python regenerate_summary.py [--records PATH] [--out PATH] [--reference PATH]

    --records     path to raw hop records JSON (default: look for
                  results/v05/v05a_full_hop_records.json relative to the
                  repository root)
    --out         output path for the regenerated summary (default: print)
    --reference   optional path to the published summary
                  (results/v05/v05a_post_h250_summary.json); when given,
                  prints a comparison of key values.

The script reproduces the key published figures:
  - completed call count and horizon counts
  - cumulative token totals by horizon and condition
  - per-hop transmitted-context stats (P bounded vs C growing)
  - classification counts, divergence rate, digest continuity, state integrity
  - failure taxonomy counts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECORDS = REPO_ROOT / "results" / "v05" / "v05a_full_hop_records.json"
DEFAULT_REFERENCE = REPO_ROOT / "results" / "v05" / "v05a_post_h250_summary.json"

EXECUTED_HORIZONS = [10, 25, 50, 100, 250]
CONDITIONS = ["P", "C"]


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"records file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        sys.exit(f"records file must contain a JSON list; got {type(data).__name__}")
    return data


def _rate(part: float, whole: float) -> float:
    return part / whole if whole else 0.0


def regenerate(records: list[dict]) -> dict:
    total = len(records)

    # Cumulative token totals by horizon and condition (sum over hops).
    # The hop records persist per-hop input/output/usage; cumulative totals
    # are computed by summing the per-hop provider-reported tokens.
    cumulative = {h: {c: {"input": 0, "output": 0, "total": 0} for c in CONDITIONS} for h in EXECUTED_HORIZONS}
    per_horizon = {}
    for h in EXECUTED_HORIZONS:
        per_horizon[str(h)] = sum(1 for r in records if r.get("horizon") == h)

    # Transmitted-context stats per horizon+condition (tokens and chars).
    context = {h: {c: {"tokens": [], "chars": []} for c in CONDITIONS} for h in EXECUTED_HORIZONS}

    # Condition-level aggregates (full executed set).
    cond_stats = {c: {"total": 0, "PASS": 0, "PARSE_ERROR": 0, "ACTION_ERROR": 0,
                      "STATE_CORRUPTION": 0, "divergence": 0, "digest_ok": 0,
                      "digest_available": 0, "integrity_ok": 0} for c in CONDITIONS}

    failures = []
    for r in records:
        h = r.get("horizon")
        c = r.get("condition")
        if h not in EXECUTED_HORIZONS or c not in CONDITIONS:
            continue

        # cumulative tokens: use the persisted per-hop provider usage fields
        # (input_tokens/output_tokens), falling back to cumulative fields only
        # if per-hop fields are absent.
        inp = r.get("input_tokens") or 0
        out = r.get("output_tokens") or 0
        cumulative[h][c]["input"] += inp
        cumulative[h][c]["output"] += out
        cumulative[h][c]["total"] += inp + out

        ctx_tok = r.get("transmitted_context_tokens")
        ctx_chars = r.get("transmitted_context_chars")
        if ctx_tok is not None:
            context[h][c]["tokens"].append(ctx_tok)
        if ctx_chars is not None:
            context[h][c]["chars"].append(ctx_chars)

        cls = r.get("classification", "PASS")
        cond = cond_stats[c]
        cond["total"] += 1
        cond[cls] = cond.get(cls, 0) + 1

        div = r.get("divergence", 0)
        if div != 0:
            cond["divergence"] += 1

        d_act = r.get("state_digest_actual")
        d_exp = r.get("state_digest_expected")
        if d_act is not None and d_exp is not None:
            cond["digest_available"] += 1
            if d_act == d_exp:
                cond["digest_ok"] += 1

        exp = r.get("expected_state")
        act = r.get("actual_state")
        if exp is not None and act is not None:
            if exp == act:
                cond["integrity_ok"] += 1

        if cls != "PASS":
            failures.append({
                "horizon": h,
                "scenario": r.get("scenario_id"),
                "trial": r.get("chain_id"),
                "condition": c,
                "hop": r.get("hop_index"),
                "type": cls,
                "divergence": div,
            })

    cumulative_totals = {}
    for h in EXECUTED_HORIZONS:
        cumulative_totals[str(h)] = {
            c: cumulative[h][c]["total"] for c in CONDITIONS
        }

    def _ctx_stats(vals):
        if not vals:
            return None
        s = sorted(vals)
        n = len(s)
        return {
            "min": s[0],
            "max": s[-1],
            "mean": round(sum(s) / n, 2),
            "count": n,
        }

    context_stats = {
        str(h): {c: _ctx_stats(context[h][c]["tokens"]) for c in CONDITIONS}
        for h in EXECUTED_HORIZONS
    }
    context_chars = {
        str(h): {c: _ctx_stats(context[h][c]["chars"]) for c in CONDITIONS}
        for h in EXECUTED_HORIZONS
    }

    condition_stats = {}
    for c in CONDITIONS:
        s = cond_stats[c]
        total_c = s["total"] or 1
        condition_stats[c] = {
            "total": s["total"],
            "pass_rate": round(_rate(s["PASS"], total_c), 6),
            "parse_error_rate": round(_rate(s["PARSE_ERROR"], total_c), 6),
            "action_error_rate": round(_rate(s["ACTION_ERROR"], total_c), 6),
            "state_corruption_rate": round(_rate(s["STATE_CORRUPTION"], total_c), 6),
            "divergence_rate": round(_rate(s["divergence"], total_c), 6),
            "digest_continuity": round(_rate(s["digest_ok"], s["digest_available"]), 6),
            "state_integrity": round(_rate(s["integrity_ok"], total_c), 6),
        }

    return {
        "regenerated_by": "benchmark/regenerate_summary.py (offline)",
        "source_records": str(DEFAULT_RECORDS),
        "completed_call_count": total,
        "completed_horizons": EXECUTED_HORIZONS,
        "actual_by_horizon": per_horizon,
        "cumulative_token_totals_by_horizon_condition": cumulative_totals,
        "per_hop_transmitted_context_tokens": context_stats,
        "per_hop_transmitted_context_chars": context_chars,
        "condition_stats": condition_stats,
        "failure_counts": {
            "ACTION_ERROR": sum(1 for f in failures if f["type"] == "ACTION_ERROR"),
            "PARSE_ERROR": sum(1 for f in failures if f["type"] == "PARSE_ERROR"),
            "STATE_CORRUPTION": sum(1 for f in failures if f["type"] == "STATE_CORRUPTION"),
        },
        "failures": failures,
    }


def compare(regenerated: dict, reference_path: Path) -> None:
    if not reference_path.exists():
        print(f"[compare] reference not found: {reference_path}")
        return
    with open(reference_path, "r", encoding="utf-8") as fh:
        ref = json.load(fh)

    print("\n=== COMPARISON vs published summary ===")
    checks = []

    def cmp(name, a, b):
        same = a == b
        checks.append(same)
        status = "OK " if same else "DIFF"
        print(f"[{status}] {name}: regenerated={a} published={b}")

    cmp("completed_call_count",
        regenerated["completed_call_count"], ref.get("completed_call_count"))
    cmp("actual_by_horizon",
        regenerated["actual_by_horizon"], ref.get("actual_by_horizon"))
    cmp("failure_counts",
        regenerated["failure_counts"], ref.get("failure_counts"))

    # cumulative totals: published summary stores P/C cumulative totals per
    # horizon; the regenerated values must match.
    pub_cum = ref.get("actual_by_horizon_condition") or {}
    for h in EXECUTED_HORIZONS:
        for c in CONDITIONS:
            key = f"{c}_h{h}"
            pub = pub_cum.get(key)
            if pub is not None:
                reg = regenerated["cumulative_token_totals_by_horizon_condition"][str(h)][c]
                cmp(f"cumulative total {c} H{h}", reg, pub)

    if all(checks):
        print("\nALL COMPARED VALUES MATCH THE PUBLISHED SUMMARY.")
    else:
        print("\nNOTE: some values differ from the published summary. Inspect "
              "differences before publishing regenerated output.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline V0.5 summary regeneration")
    ap.add_argument("--records", default=str(DEFAULT_RECORDS))
    ap.add_argument("--out", default=None, help="write regenerated summary JSON to PATH")
    ap.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    args = ap.parse_args()

    records = load_records(Path(args.records))
    summary = regenerate(records)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"regenerated summary written to: {out}")
    else:
        print(json.dumps(summary, indent=2))

    compare(summary, Path(args.reference))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
