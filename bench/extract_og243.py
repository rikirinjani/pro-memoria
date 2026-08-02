import json
from pathlib import Path

d = Path.home() / "self-harness" / "traces"
all_traces = []
for f in sorted(d.glob("*.pm1")):
    try:
        p = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        if p.get("pm1_version") == 1:
            all_traces.append((p.get("timestamp", ""), p))
    except:
        pass

all_traces.sort(key=lambda x: x[0])
og_243 = [t for _, t in all_traces[:243]]
out = Path(__file__).resolve().parent / "results" / "original_243_traces.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(og_243, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Written {len(og_243)} traces to {out}")
print(f"Range: {all_traces[0][0][:19]} to {all_traces[242][0][:19]}")
print(f"Size: {out.stat().st_size/1024:.0f} KB")
