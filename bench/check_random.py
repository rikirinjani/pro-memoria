import json
from collections import Counter

d = json.load(open("bench/results/mechanical_random_sample.json", encoding="utf-8"))
events = d.get("events", d) if isinstance(d, dict) else d

counts = Counter()
flips = 0
for e in events:
    auto = e.get("auto_label", "mechanical")
    human = e.get("human_label", "?")
    counts[human] += 1
    if auto != human:
        flips += 1
        action = e.get("first_action", "")[:80]
        print(f"  FLIP: {auto} -> {human}: {action}")

print(f"\nTotal: {len(events)}")
print(f"Flips: {flips}")
for lbl, cnt in counts.most_common():
    print(f"  {lbl}: {cnt}")

if flips > 0:
    flip_rate = flips / len(events)
    false_mech = round(flip_rate * 260)
    adj_mech = 260 - false_mech
    print(f"\nFlip rate in sample: {flips}/{len(events)} = {flip_rate*100:.0f}%")
    print(f"Estimated false-mechanical in full 260: {false_mech}")
    print(f"Adjusted mechanical: {adj_mech} / 374 = {adj_mech/374*100:.1f}%")
else:
    print("\nNo flips -- 69.5% holds.")
