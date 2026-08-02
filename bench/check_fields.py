import json
from pathlib import Path
from collections import Counter

d = Path.home() / "self-harness" / "traces"

# Check what fields exist that could serve as dedup keys
field_samples = Counter()
session_ids = set()
slug_ids = set()
keyfile_refs = Counter()

for f in sorted(d.glob("*.pm1")):
    try:
        p = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        if p.get("pm1_version") == 1:
            # What non-encoding fields exist?
            for k in p:
                if k not in ("pm1", "pm1_version", "encoding", "state_width", "n_states", "failsafe", "savings", "ratio"):
                    field_samples[k] += 1
            
            sid = p.get("session_id", "")
            if sid: session_ids.add(sid)
            
            slug = p.get("slug", "")
            if slug: slug_ids.add(slug)
            
            # Key files as event anchors
            kfs = p.get("key_files", [])
            if kfs:
                for kf in kfs:
                    # Extract project/file stem as potential event ID
                    parts = Path(kf).parts
                    if parts:
                        keyfile_refs[parts[-1].rsplit(".", 1)[0]] += 1
    except:
        pass

print("Fields in traces (>10% presence):")
for field, count in field_samples.most_common(30):
    pct = count / max(len(session_ids), 1) * 100
    if pct > 5:
        print(f"  {field}: {count} ({pct:.0f}%)")

print(f"\nUnique session_ids: {len(session_ids)}")
print(f"Unique slugs: {len(slug_ids)}")

# Top key_file stems (potential event anchors)
print(f"\nTop key_file stems (potential event identifiers):")
for stem, count in keyfile_refs.most_common(15):
    print(f"  {stem}: {count}")
