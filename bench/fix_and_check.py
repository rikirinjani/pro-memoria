import re, json

raw = open("bench/results/mechanical_random_sample.json", encoding="utf-8").read()
# Fix: missing commas + indentation issues between auto_label and human_label
fixed = re.sub(
    r'"auto_label": "(\w+)"\n\s*"human_label": "(\w+)"',
    r'"auto_label": "\1",\n      "human_label": "\2"',
    raw
)
d = json.loads(fixed)
open("bench/results/mechanical_random_sample.json", "w", encoding="utf-8").write(fixed)
print(f"Fixed. Parsed {len(d.get('events', []))} events.")

# Now count
from collections import Counter
counts = Counter()
flips = 0
for e in d["events"]:
    auto = e.get("auto_label", "mechanical")
    human = e.get("human_label", "?")
    counts[human] += 1
    if auto != human:
        flips += 1
        print(f"  FLIP: {auto} -> {human}: {e.get('first_action','')[:80]}")

print(f"\nTotal: {len(d['events'])}")
print(f"Flips: {flips}")
for lbl, cnt in counts.most_common():
    print(f"  {lbl}: {cnt}")

if flips > 0:
    rate = flips / len(d["events"])
    false_mech = round(rate * 260)
    adj_mech = 260 - false_mech
    print(f"\nFlip rate: {flips}/{len(d['events'])} = {rate*100:.0f}%")
    print(f"Estimated false-mechanical: {false_mech}")
    print(f"Adjusted mechanical: {adj_mech} / 374 = {adj_mech/374*100:.1f}%")
else:
    print("\nNo flips -- 69.5% holds.")
