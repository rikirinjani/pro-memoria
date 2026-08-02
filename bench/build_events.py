"""Hermes coordination event builder + consequence-based labelling.
Rebuilds the classifier per reviewer feedback:
- Unit of analysis: coordination EVENT, not trace
- Dedup key: key_file overlap + 10-min timestamp window
- Label question: "Would Hermes have needed to wake an LLM?"
- Oversamples the mechanical/semantic boundary for human validation
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta

TRACES_DIR = Path.home() / "self-harness" / "traces"
OUT_DIR = Path(__file__).resolve().parent.parent / "bench" / "results"
OUT_DIR.mkdir(exist_ok=True)

# ── Load traces ─────────────────────────────────────────────────────────

def load_traces():
    traces = []
    for f in sorted(TRACES_DIR.glob("*.pm1")):
        try:
            p = json.loads(f.read_text(encoding="utf-8", errors="replace"))
            if p.get("pm1_version") == 1:
                traces.append(p)
        except:
            pass
    return sorted(traces, key=lambda t: t.get("timestamp", ""))

traces = load_traces()
print(f"Loaded {len(traces)} traces")

# ── Dedup into coordination events ──────────────────────────────────────

def parse_ts(ts_str):
    """Parse ISO timestamp to datetime."""
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except:
        return datetime.min.replace(tzinfo=timezone.utc)

def key_file_set(trace):
    """Return set of filename stems from key_files."""
    kfs = trace.get("key_files", []) or []
    return {Path(kf).stem for kf in kfs}

def build_events(traces, window_minutes=10):
    """
    Group traces into coordination events.
    Two traces belong to the same event if:
    - They share at least 1 key_file stem, AND
    - Their timestamps are within `window_minutes` of each other.
    Traces with no key_files are kept as singleton events.
    """
    # Build time-keyed index
    by_minute = defaultdict(list)
    for t in traces:
        ts = parse_ts(t.get("timestamp", ""))
        minute_key = ts.replace(second=0, microsecond=0)
        by_minute[minute_key].append(t)

    # Assign each trace to an event group via union-find over time windows
    parent = {}
    def find(x):
        while parent[x] != x:
            parent.setdefault(x, x)
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Index traces by their identity
    trace_ids = {id(t): t for t in traces}
    for tid in trace_ids:
        parent.setdefault(tid, tid)

    # Union traces that share key_files within the time window
    window = timedelta(minutes=window_minutes)
    sorted_minutes = sorted(by_minute.keys())

    for i, minute in enumerate(sorted_minutes):
        # Look at traces within the window
        for j in range(i, len(sorted_minutes)):
            other = sorted_minutes[j]
            if other - minute > window:
                break
            # Compare traces in these minute buckets
            for t1 in by_minute[minute]:
                kfs1 = key_file_set(t1)
                if not kfs1:
                    continue
                for t2 in by_minute[other]:
                    if id(t1) == id(t2):
                        continue
                    kfs2 = key_file_set(t2)
                    if not kfs2:
                        continue
                    if kfs1 & kfs2:  # shared key_file
                        union(id(t1), id(t2))

    # Group traces into events
    events = defaultdict(list)
    for t in traces:
        root = find(id(t))
        events[root].append(t)

    # Sort events by earliest timestamp
    event_list = []
    for root, group in events.items():
        group.sort(key=lambda t: t.get("timestamp", ""))
        event_list.append(group)

    event_list.sort(key=lambda g: g[0].get("timestamp", ""))

    # Label each event as singleton or multi-trace
    singletons = sum(1 for g in event_list if len(g) == 1)
    multi = sum(1 for g in event_list if len(g) > 1)
    print(f"Events: {len(event_list)} total ({singletons} singletons, {multi} multi-trace)")
    print(f"Dedup ratio: {len(traces)} traces -> {len(event_list)} events ({len(event_list)/len(traces)*100:.1f}%)")

    return event_list

events = build_events(traces, window_minutes=10)

# ── Consequence-based labelling ─────────────────────────────────────────

def label_event(event_traces):
    """
    Answer: "Would Hermes have needed to wake an LLM for this coordination event?"
    
    MECHANICAL: A deterministic scheduler can decide the next action.
        - outcome is pass/fail with no failure diagnosis needed
        - action is a routine state transition (trace recording, file ops, build, deploy)
        - no semantic judgment required
    
    SEMANTIC: An LLM must reason about the event to decide next steps.
        - failure with root cause analysis needed
        - confidence change, unexpected finding, contradiction
        - decision required (choose between options, evaluate quality)
        - analysis, review, investigation, diagnosis
    
    DELIVERABLE: Output intended for human consumption.
        - paper, report, manuscript, publication
        - summary for human review
        - completed deliverable (not a status update, the actual output)
    """
    # Collect signals from all traces in the event
    actions = [t.get("action", "") for t in event_traces]
    outcomes = [t.get("outcome", "") for t in event_traces]
    agents = [t.get("agent", "") for t in event_traces]
    failures = [t.get("failure", {}) for t in event_traces]
    key_files_all = []
    for t in event_traces:
        kfs = t.get("key_files", []) or []
        key_files_all.extend(kfs)
    
    combined_action = " ".join(actions).lower()
    has_failure = any(f.get("category") for f in failures)
    has_fail = any(o == "fail" for o in outcomes)
    all_pass = all(o == "pass" for o in outcomes)
    
    # ── Deliverable check ────────────────────────────────────────────
    deliverable_keywords = [
        "paper", "manuscript", "report", "published", "released",
        "submitted", "finalized", "shipped", "delivered",
        "draft for", "write paper", "generate pdf",
    ]
    for kw in deliverable_keywords:
        if kw in combined_action:
            return "deliverable"
    
    # Check if key_files suggest a deliverable
    deliverable_files = ["pro-memoria.md", "pro-memoria.pdf", "README.md",
                         "paper", "report.md", "manuscript"]
    for kf in key_files_all:
        kf_lower = kf.lower()
        for df in deliverable_files:
            if df in kf_lower:
                # Only if the action is about finalizing/submitting
                if any(w in combined_action for w in ["final", "complete", "submit", "publish", "release"]):
                    return "deliverable"
    
    # ── Semantic check ───────────────────────────────────────────────
    # Does this event require reasoning to determine the next action?
    semantic_indicators = [
        # Failure that needs diagnosis
        has_failure and has_fail,
        # Debug/troubleshoot actions
        any(w in combined_action for w in ["debug", "diagnos", "investigat",
                "root cause", "trace back", "isolate", "why", "underlying"]),
        # Analysis and review
        any(w in combined_action for w in ["analyzed", "reviewed", "evaluated",
                "assessed", "compared", "critiqued", "judged"]),
        # Discovery and uncertainty
        any(w in combined_action for w in ["discovered", "found contradict",
                "unexpected", "surprising", "novel", "insight"]),
        # Decision-making
        any(w in combined_action for w in ["decided", "chose", "selected",
                "determined", "concluded", "recommended"]),
        # Planning / strategy
        any(w in combined_action for w in ["planned", "designed", "architected",
                "strateg", "roadmap"]),
        # Research that synthesized findings
        any(w in combined_action for w in ["researched", "synthesized",
                "compiled comprehensive", "literature review"]),
        # Confidence / quality assessment
        any(w in combined_action for w in ["confidence", "quality check",
                "validated against", "verified against", "cross-reference"]),
    ]
    
    if any(semantic_indicators):
        return "semantic"
    
    # ── Mechanical check ─────────────────────────────────────────────
    # Can a deterministic scheduler handle this?
    mechanical_indicators = [
        all_pass and not has_failure,
        all_pass and has_failure and not has_fail,  # failure recorded but resolved mechanically
        any(w in combined_action for w in ["wrote", "created", "updated", "added",
                "removed", "fixed", "pushed", "committed", "merged",
                "built", "ran", "tested", "verified", "checked"]),
        any(w in combined_action for w in ["trace", "recorded", "logged",
                "reconciled", "retroactive", "session wrap"]),
        any(w in combined_action for w in ["scaffold", "scaffolded", "configured",
                "installed", "setup", "initialized"]),
        any(w in combined_action for w in ["moved", "copied", "renamed",
                "translated", "converted", "parsed"]),
    ]
    
    if any(mechanical_indicators):
        return "mechanical"
    
    # ── Fallback ─────────────────────────────────────────────────────
    # Default to semantic for anything we can't confidently classify as mechanical
    return "semantic"

# ── Label all events ────────────────────────────────────────────────────

results = {"mechanical": [], "semantic": [], "deliverable": []}
boundary_events = []  # Events near the mechanical/semantic border

for event in events:
    label = label_event(event)
    results[label].append(event)

total_events = sum(len(v) for v in results.values())
mech_events = len(results["mechanical"])
sem_events = len(results["semantic"])
deliv_events = len(results["deliverable"])

print(f"\n=== Event-level classification ({total_events} events) ===")
print(f"  Mechanical:  {mech_events:4d} ({mech_events/total_events*100:5.1f}%)")
print(f"  Semantic:    {sem_events:4d} ({sem_events/total_events*100:5.1f}%)")
print(f"  Deliverable: {deliv_events:4d} ({deliv_events/total_events*100:5.1f}%)")

# Also compute trace-level for comparison
trace_results = {"mechanical": 0, "semantic": 0, "deliverable": 0}
for event in events:
    label = label_event(event)
    trace_results[label] += len(event)
total_traces = sum(trace_results.values())
print(f"\n=== Trace-level for comparison ===")
print(f"  Mechanical:  {trace_results['mechanical']:4d} ({trace_results['mechanical']/total_traces*100:5.1f}%)")
print(f"  Semantic:    {trace_results['semantic']:4d} ({trace_results['semantic']/total_traces*100:5.1f}%)")
print(f"  Deliverable: {trace_results['deliverable']:4d} ({trace_results['deliverable']/total_traces*100:5.1f}%)")

# ── Identify boundary events for human validation ───────────────────────

# Boundary: events where the classification is ambiguous
# These are cases where mechanical/semantic indicators are mixed
for event in events:
    actions = [t.get("action", "") for t in event]
    combined = " ".join(actions).lower()
    
    # Mixed signals: pass outcome but action sounds like analysis
    outcomes = [t.get("outcome", "") for t in event]
    all_pass = all(o == "pass" for o in outcomes)
    
    # Pass outcome + research/analysis verb = boundary
    if all_pass and any(w in combined for w in [
        "researched", "analyzed", "investigated", "explored",
        "compared", "evaluated", "reviewed", "synthesized",
        "compiled", "assessed"
    ]):
        label = label_event(event)
        boundary_events.append({
            "label": label,
            "traces": len(event),
            "first_action": actions[0][:120] if actions else "",
            "agents": list(set(t.get("agent", "") for t in event)),
            "outcomes": list(set(t.get("outcome", "") for t in event)),
        })

print(f"\n=== Boundary events (ambiguous mechanical/semantic): {len(boundary_events)} ===")

# ── Write output ────────────────────────────────────────────────────────

# Full event list with labels
event_output = []
for i, event in enumerate(events):
    label = label_event(event)
    trace_summaries = []
    for t in event:
        trace_summaries.append({
            "agent": t.get("agent", "?"),
            "outcome": t.get("outcome", "?"),
            "action": (t.get("action") or "")[:120],
            "key_files": t.get("key_files", [])[:5],
            "timestamp": (t.get("timestamp") or "")[:19],
        })
    event_output.append({
        "event_id": i + 1,
        "class": label,
        "trace_count": len(event),
        "traces": trace_summaries,
    })

# JSON output
events_json = OUT_DIR / "coordination_events_labeled.json"
events_json.write_text(json.dumps({
    "total_traces": len(traces),
    "total_events": total_events,
    "dedup_ratio": round(total_events / len(traces), 3),
    "mechanical": {"events": mech_events, "pct": round(mech_events / total_events * 100, 1)},
    "semantic": {"events": sem_events, "pct": round(sem_events / total_events * 100, 1)},
    "deliverable": {"events": deliv_events, "pct": round(deliv_events / total_events * 100, 1)},
    "boundary_events_count": len(boundary_events),
    "methodology": "coordination-event-level, key_file+time-window dedup, consequence-based labelling",
    "events": event_output,
    "boundary_events": boundary_events,
}, indent=2, ensure_ascii=False), encoding="utf-8")

# Boundary events for human validation
boundary_json = OUT_DIR / "boundary_events_human_validation.json"
boundary_json.write_text(json.dumps({
    "count": len(boundary_events),
    "instruction": "For each event, answer: 'Would Hermes have needed to wake an LLM for this coordination decision?' Mark as mechanical/semantic/deliverable.",
    "events": boundary_events,
}, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"\nOutputs:")
print(f"  {events_json}")
print(f"  {boundary_json}")
print(f"\nAmdahl ceiling (event-level): {mech_events/total_events*100:.1f}% mechanical")
print(f"Amdahl ceiling (trace-level): {trace_results['mechanical']/total_traces*100:.1f}% mechanical")
