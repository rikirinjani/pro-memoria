import json
from pathlib import Path

d = Path.home() / "self-harness" / "traces"
traces = []
for f in sorted(d.glob("*.pm1")):
    try:
        p = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        if p.get("pm1_version") == 1:
            traces.append((p.get("timestamp", ""), p))
    except:
        pass
traces.sort(key=lambda x: x[0])
og = [t for _, t in traces]

out = Path(__file__).resolve().parent / "results" / "original_518_traces.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(og, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Written {len(og)} traces to {out} ({out.stat().st_size/1024:.0f} KB)")
