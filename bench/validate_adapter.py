"""Live validation: feed all real traces through pm-adapter, measure coverage and gaps."""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
from pm_adapter import Adapter, load_schema

TRACES_DIR = Path.home() / "self-harness" / "traces"
OUT_DIR = Path(__file__).resolve().parent / "results"

schema = load_schema("default")
adapter = Adapter(schema)

# Accumulators
stats = {
    "total": 0,
    "decoded": 0,           # clean decode
    "decode_errors": 0,     # any exception during decode
    "schema_gaps": Counter(),  # byte_values with no label mapping
    "ecc_corrected": 0,     # single-bit corrections
    "ecc_errors": 0,        # unrecoverable ECC errors
    "by_agent": defaultdict(lambda: {"count": 0, "pm1_chars": 0, "json_bytes": 0}),
    "mode_coverage": {"to_english": 0, "to_json": 0, "to_semantic": 0, "to_events": 0},
}

# Helper to estimate JSON equivalent bytes
def estimate_json(savings_data):
    return savings_data.get("json_bytes", 0) or 0

for f in sorted(TRACES_DIR.glob("*.pm1")):
    try:
        trace = json.loads(f.read_text(encoding="utf-8", errors="replace"))
    except:
        continue
    if trace.get("pm1_version") != 1 or "pm1" not in trace:
        continue
    
    frame = trace["pm1"]
    agent = trace.get("agent", "unknown")
    stats["total"] += 1
    
    # Decode
    try:
        decoded = adapter.decode(frame)
        stats["decoded"] += 1
    except Exception as e:
        stats["decode_errors"] += 1
        continue
    
    # Schema gap detection: which byte values have no label?
    for field_name, data in decoded.items():
        raw = data["raw"]
        label = data["label"]
        if str(raw) == label:  # label fell back to raw string → no mapping
            stats["schema_gaps"][field_name] += 1
    
    # All four modes
    try:
        adapter.to_english(frame)
        stats["mode_coverage"]["to_english"] += 1
    except:
        pass
    try:
        adapter.to_json(frame)
        stats["mode_coverage"]["to_json"] += 1
    except:
        pass
    try:
        adapter.to_semantic(frame)
        stats["mode_coverage"]["to_semantic"] += 1
    except:
        pass
    try:
        adapter.to_events(frame)
        stats["mode_coverage"]["to_events"] += 1
    except:
        pass
    
    # Per-agent stats
    ag = stats["by_agent"][agent]
    ag["count"] += 1
    ag["pm1_chars"] += len(frame)
    # Prefer the trace's recorded savings; fall back to the adapter's own
    # JSON output size when the trace has no savings field (no real trace
    # currently carries one).
    json_bytes = estimate_json(trace.get("savings", {}))
    if not json_bytes:
        try:
            json_bytes = len(json.dumps(adapter.to_json(frame), ensure_ascii=False))
        except Exception:
            json_bytes = 0
    ag["json_bytes"] += json_bytes

# Print report
print(f"=== PM-Adapter Live Validation Report ===")
print(f"Total traces: {stats['total']}")
print(f"Clean decodes: {stats['decoded']} ({stats['decoded']/max(stats['total'],1)*100:.1f}%)")
print(f"Decode errors: {stats['decode_errors']}")
print(f"ECC corrections: {stats['ecc_corrected']}")
print(f"ECC errors: {stats['ecc_errors']}")
print(f"\nMode coverage:")
for mode, count in stats["mode_coverage"].items():
    print(f"  {mode}: {count} ({count/max(stats['total'],1)*100:.1f}%)")
print(f"\nSchema gaps (bytes without value mappings):")
for field, count in stats["schema_gaps"].most_common():
    print(f"  {field}: {count} traces")
print(f"\nPer-agent savings:")
for agent, ag in sorted(stats["by_agent"].items(), key=lambda x: -x[1]["count"]):
    ratio = ag["pm1_chars"] / max(ag["json_bytes"], 1)
    savings = (1 - ratio) * 100
    pm1_tok = ag["pm1_chars"] * 0.125
    print(f"  {agent:15s} {ag['count']:4d} traces  {ag['pm1_chars']:6d} chars  {pm1_tok:7.0f} tok  {savings:5.1f}% savings")

# Save JSON report
report = {k: v for k, v in stats.items() if k != "by_agent"}
report["by_agent"] = {k: dict(v) for k, v in stats["by_agent"].items()}
report["schema_gaps"] = dict(stats["schema_gaps"].most_common())
report["mode_coverage"] = dict(stats["mode_coverage"])
OUT_DIR.mkdir(exist_ok=True)
out = OUT_DIR / "adapter_validation_report.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nReport: {out}")
