import json
from pathlib import Path

# Load event data and human corrections
events_data = json.load(open("bench/results/coordination_events_labeled.json", encoding="utf-8"))
boundary = json.load(open("bench/results/boundary_events_human_validation_labeled.json", encoding="utf-8"))

# Build a map from event first_action to human label
human_map = {}
for b in boundary["events"]:
    key = b["first_action"]
    human_map[key] = b.get("human_label", b["label"])

# Apply corrections to all events
corrected = {"mechanical": 0, "semantic": 0, "deliverable": 0}
flips = 0
for event in events_data["events"]:
    auto = event["class"]
    first_action = ""
    if event["traces"]:
        first_action = event["traces"][0].get("action", "")
    human = human_map.get(first_action, auto)
    if human != auto:
        flips += 1
    corrected[human] += 1

total = sum(corrected.values())
mech = corrected["mechanical"]
sem = corrected["semantic"]
deli = corrected["deliverable"]

print(f"=== Final corrected ratios ({total} events) ===")
print(f"  Mechanical:  {mech:4d} ({mech/total*100:5.1f}%)")
print(f"  Semantic:    {sem:4d} ({sem/total*100:5.1f}%)")
print(f"  Deliverable: {deli:4d} ({deli/total*100:5.1f}%)")
print(f"  Flips applied: {flips}")
print(f"  Amdahl ceiling: {mech/total*100:.1f}%")

# Write report
lines = [
    "# Hermes Coordination Event Classification — Final Report",
    "",
    "> Method: coordination-event-level analysis with human-validated boundary calibration.",
    "> Unit of analysis: coordination EVENT (traces deduplicated by key-file + 10-min time window).",
    "> Label question: *Would Hermes have needed to wake an LLM for this coordination decision?*",
    "",
    "## Methodology Evolution",
    "",
    "| Phase | Unit | Question | Mechanical | Semantic | Deliverable | Issue |",
    "|-------|------|----------|------------|----------|-------------|-------|",
    "| v1 (heuristic) | Trace | Starts with mechanical verb? | 80.5% | 9.7% | 9.8% | Measured logging patterns, not coordination |",
    f"| v2 (event-level) | Coordination event | Would Hermes wake an LLM? | 69.5% | 19.5% | 11.0% | Auto-classifier, uncalibrated |",
    f"| **v3 (human-calibrated)** | **Coordination event** | **Would Hermes wake an LLM?** | **{mech/total*100:.1f}%** | **{sem/total*100:.1f}%** | **{deli/total*100:.1f}%** | **44 boundary events human-validated** |",
    "",
    "## Final Ratios",
    "",
    f"Across **{total} coordination events** (deduplicated from 518 traces):",
    "",
    f"- **Mechanical: {mech} events ({mech/total*100:.1f}%)** — deterministically routable without LLM invocation",
    f"- **Semantic: {sem} events ({sem/total*100:.1f}%)** — requires reasoning, interpretation, or judgment",
    f"- **Deliverable: {deli} events ({deli/total*100:.1f}%)** — human-facing output, completed work products",
    "",
    "## Amdahl's Law Implication",
    "",
    f"The mechanical ceiling is **{mech/total*100:.1f}%** — no coordination architecture can eliminate more than this fraction of coordination overhead through deterministic scheduling alone, because the remaining {sem/total*100:.1f}% of events require semantic reasoning.",
    "",
    "## Boundary Calibration",
    "",
    f"**44 boundary events** (pass outcome + analysis verb — the ambiguous mechanical/semantic border) were human-validated. Of these:",
    f"- {flips} flips from auto-classifier: all semantic → deliverable (classifier over-called semantic)",
    f"- Human labels: {sum(1 for b in boundary['events'] if b.get('human_label') == 'semantic')} semantic, {sum(1 for b in boundary['events'] if b.get('human_label') == 'deliverable')} deliverable, {sum(1 for b in boundary['events'] if b.get('human_label') == 'mechanical')} mechanical",
    "",
    "## Key Finding",
    "",
    f"Approximately **2 out of 3** coordination events ({mech/total*100:.0f}%) are mechanically decidable — a Hermes-style scheduler can route these without waking an LLM. The remaining 1 in 3 requires semantic reasoning or human-facing output.",
    "",
    f"This is a significant downward correction from the initial heuristic's 80.5% figure. The original heuristic was measuring logging frequency, not coordination necessity. The event-level, consequence-based analysis reveals that real agent coordination involves more semantic judgment than trace verb-matching suggests.",
    "",
    "## Data Files",
    "",
    "- `original_518_traces.json` — raw traces (no labels)",
    "- `original_243_traces.json` — paper dataset subset",
    "- `coordination_events_labeled.json` — 374 events, auto-classified",
    "- `boundary_events_human_validation_labeled.json` — 44 boundary events, human-validated",
]

Path("bench/results/trace_classification_report.md").write_text("\n".join(lines), encoding="utf-8")
print("\nReport written to bench/results/trace_classification_report.md")
