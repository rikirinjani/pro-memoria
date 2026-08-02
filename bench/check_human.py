import json
from collections import Counter

d = json.load(open("bench/results/boundary_events_human_validation_labeled.json", encoding="utf-8"))
events = d.get("events", d) if isinstance(d, dict) else d

counts = Counter()
flips = 0
for e in events:
    auto = e.get("label", "?")
    human = e.get("human_label", "?")
    counts[human] += 1
    if auto != human:
        flips += 1

print(f"Total: {len(events)}")
print(f"Flips (auto->human changed): {flips}")
for lbl, cnt in counts.most_common():
    print(f"  {lbl}: {cnt} ({cnt/len(events)*100:.0f}%)")
print()
print("Label changes:")
for e in events:
    if e.get("label") != e.get("human_label"):
        action = e.get("first_action", "")[:80]
        print(f"  {e['label']} -> {e['human_label']}: {action}")
