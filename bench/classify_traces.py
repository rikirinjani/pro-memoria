"""Classify each trace into Mechanical / Semantic / Deliverable buckets.
Implements the three-class split from the Hermes architecture discussion.
"""
import json
import sys
from pathlib import Path

TRACES_DIR = Path.home() / "self-harness" / "traces"

# ── Classification rules ───────────────────────────────────────────────

MECHANICAL_ACTIONS = {
    "wrote", "created", "updated", "pushed", "moved", "copied",
    "added", "removed", "fixed", "deployed", "generated", "ran",
    "built", "committed", "installed", "configured", "validated",
    "checked", "verified", "tested", "recorded", "reconciled",
    "regenerated", "refreshed", "opened", "closed", "completed",
    "finished", "scaffold", "scaffolded", "audit", "tagged",
    "indexed", "logged", "tracked", "counted", "compiled",
    "edited", "renamed", "translated", "converted", "parsed",
    "saved", "loaded", "read", "fetched", "retrieved",
    "extracted", "imported", "exported", "synced", "merged",
    "initialized", "setup", "cleaned", "pruned", "deleted",
    "drafted", "wrote"   # mechanical writing (traces, drafts, edits)
}

SEMANTIC_ACTIONS = {
    "analyzed", "reviewed", "compared", "evaluated", "assessed",
    "decided", "judged", "determined", "diagnosed", "identified",
    "investigated", "explored", "discovered", "found", "noticed",
    "reasoned", "considered", "weighed", "balanced", "chose",
    "selected", "recommended", "suggested", "proposed",
    "critiqued", "questioned", "challenged", "argued",
    "interpreted", "understood", "realized", "predicted",
    "estimated", "approximated", "inferred", "concluded",
    "synthesized", "combined", "integrated", "correlated",
    "mapped", "connected", "linked", "related",
    "planned", "strategized", "designed", "architected",
    "refactored", "reorganized", "restructured",
    "debugged", "troubleshooted", "resolved",
    "cross-referenced", "cross_ref", "compared", "benchmark",
    "audit"   # analysis-type audits
}

DELIVERABLE_ACTIONS = {
    "published", "released", "shipped", "delivered",
    "submitted", "sent", "presented", "shared",
    "finalized", "completed", "signed off",
    "paper", "report", "manuscript", "document",
    "published", "posted", "announced",
}

# Session-wrap / session-recovery / homebase-init are mechanical
SESSION_KEYWORDS = {"session wrap", "session-wrap", "session recovery",
                     "homebase", "initialize", "retroactive", "retrace"}

# ── Classifier ──────────────────────────────────────────────────────────

def classify(trace: dict) -> str:
    """Return 'mechanical', 'semantic', or 'deliverable'."""
    action = (trace.get("action") or "").strip()
    agent = trace.get("agent", "unknown")
    outcome = trace.get("outcome", "unknown")
    slug = (trace.get("slug") or "").lower()
    has_failure = bool(trace.get("failure", {}).get("category"))

    # ── Rule 1: Session-level bookkeeping is always mechanical ──────
    action_lower = action.lower()
    for kw in SESSION_KEYWORDS:
        if kw in action_lower or kw in slug:
            return "mechanical"

    # ── Rule 2: Pure trace recording (self-referential) is mechanical ──
    if len(action) < 5:
        return "mechanical"

    # ── Rule 3: Extract the primary verb ────────────────────────────
    first_word = action.split()[0].lower().rstrip("!.,;:") if action else ""

    # ── Rule 4: Deliverable check (human output) ────────────────────
    if first_word in DELIVERABLE_ACTIONS:
        return "deliverable"
    for kw in {"paper", "report", "manuscript", "publish", "release", "ship"}:
        if kw in action_lower:
            return "deliverable"

    # ── Rule 5: Failure-driven actions need reasoning ───────────────
    if has_failure and outcome == "fail":
        # Failure diagnosis is always semantic
        if first_word in {"diagnosed", "debugged", "analyzed", "investigated",
                          "found", "discovered", "root", "traced", "isolated"}:
            return "semantic"
        # Simple failure recording (fix/completed) is mechanical
        if first_word in MECHANICAL_ACTIONS:
            return "mechanical"

    # ── Rule 6: Semantic verbs ──────────────────────────────────────
    if first_word in SEMANTIC_ACTIONS:
        return "semantic"

    # ── Rule 7: Mechanical verbs ────────────────────────────────────
    if first_word in MECHANICAL_ACTIONS:
        return "mechanical"

    # ── Rule 8: Outcome-based fallback ──────────────────────────────
    if outcome in ("pass", "fail"):
        # Clean pass/fail with unknown verb → likely mechanical
        if "analysis" not in action_lower and "review" not in action_lower:
            return "mechanical"

    # ── Rule 9: Default to semantic ─────────────────────────────────
    return "semantic"


# ── Main ────────────────────────────────────────────────────────────────

def main():
    pm1_files = sorted(TRACES_DIR.glob("*.pm1"))
    results = {"mechanical": [], "semantic": [], "deliverable": []}

    for f in pm1_files:
        try:
            trace = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        if trace.get("pm1_version") != 1:
            continue
        bucket = classify(trace)
        results[bucket].append({
            "slug": f.stem,
            "agent": trace.get("agent", "?"),
            "outcome": trace.get("outcome", "?"),
            "action": (trace.get("action") or "")[:100],
            "bucket": bucket,
        })

    total = sum(len(v) for v in results.values())

    print(f"Classification of {total} traces:\n")
    print(f"{'='*60}")

    for bucket in ("mechanical", "semantic", "deliverable"):
        count = len(results[bucket])
        pct = count / max(total, 1) * 100
        print(f"  {bucket.upper():12s}  {count:4d}  ({pct:5.1f}%)")

    print(f"{'='*60}")
    print(f"  {'TOTAL':12s}  {total:4d}")

    # ── Show a few examples from each bucket ──
    for bucket in ("mechanical", "semantic", "deliverable"):
        entries = results[bucket]
        if not entries:
            continue
        print(f"\n--- {bucket.upper()} (first 5) ---")
        for e in entries[:5]:
            try:
                print(f"  [{e['agent'][:12]:12s}] {e['action'][:90]}")
            except UnicodeEncodeError:
                print(f"  [{e['agent'][:12]:12s}] <unicode in action>")

    # ── Write detailed JSON ──
    out = Path(__file__).resolve().parent / "results" / "trace_classification.json"
    out.parent.mkdir(exist_ok=True)
    payload = {
        "total": total,
        "mechanical": len(results["mechanical"]),
        "semantic": len(results["semantic"]),
        "deliverable": len(results["deliverable"]),
        "mechanical_pct": round(len(results["mechanical"]) / max(total, 1) * 100, 1),
        "semantic_pct": round(len(results["semantic"]) / max(total, 1) * 100, 1),
        "deliverable_pct": round(len(results["deliverable"]) / max(total, 1) * 100, 1),
        "methodology": "heuristic verb + outcome classification from action field, per three-class event rubric",
        "details": results,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull output: {out}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
