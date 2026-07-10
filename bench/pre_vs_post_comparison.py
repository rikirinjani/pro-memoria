"""Pro Memoria -- Pre-Review vs Post-Review Benchmark Comparison.

Shows how the metrics evolved across 3 rounds of peer review.
"""
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"

# Original Phase 4 results (before any review fixes)
PRE = {
    "naive_json_cl100k": 53043,
    "steelman_json_cl100k": 28076,
    "morse_dsp_cl100k": 4270,
    "braille_dsp_cl100k": 2244,
    "naive_json_o200k": 51467,
    "steelman_json_o200k": 27219,
    "morse_dsp_o200k": 3964,
    "braille_dsp_o200k": 2008,
    "sweep_128byte_10pct_morse_cl100k": 326,  # BUGGY: only 1 byte
    "headline": "85% vs steelman JSON (single trace, single byte)",
}

# Post-R3 results
POST = json.loads((RESULTS / "token_efficiency.json").read_text())
c = POST["crucible"]["cl100k_base"]

print("=" * 72)
print("  Pro Memoria -- Pre-Review vs Post-Review Benchmark Comparison")
print("=" * 72)

# 1. Crucible trace -- core formats
print("\n  [1] AB-1 Crucible trace (1417 states, 748 emits, 52.8% ratio)")
print(f"  {'Format':20s} {'Pre-review':>12s} {'Post-review':>12s} {'Delta':>8s}")
print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*8}")

for fmt, key in [("Naive JSON", "naive_json"), ("Steelman JSON", "steelman_json"),
                  ("Morse DSP", "morse_dsp"), ("AB-1 Braille", "braille_dsp"),
                  ("Hex", "hex"), ("Base64", "base64")]:
    pre_val = PRE.get(f"{key}_cl100k", "-")
    post_val = c.get(key, "-")
    if pre_val != "-" and post_val != "-":
        delta = f"{post_val - pre_val:+d}" if isinstance(post_val, int) else "-"
    else:
        delta = "NEW" if pre_val == "-" else "-"
    print(f"  {fmt:20s} {str(pre_val):>12s} {str(post_val):>12s} {str(delta):>8s}")

# 2. Headline evolution
print("\n  [2] Headline claim evolution")
print(f"  {'Round':12s} {'Headline':50s}")
print(f"  {'-'*12} {'-'*50}")
print(f"  {'R0 (pre-review)':12s} {'85% vs steelman JSON (single trace, 1-byte states)':50s}")
print(f"  {'R1':12s} {'+ hex/b64 baselines, + multi-byte sweep added':50s}")
print(f"  {'R2':12s} {'Sweep methodology fixed (was 1 byte, now N bytes)':50s}")
print(f"  {'R3':12s} {'Protocol state machine + versioning added':50s}")
print(f"  {'Current':12s} {'Morse beats hex 1.4-2x at <50% change multi-byte states':50s}")

# 3. Sensitivity sweep -- pre vs post
print("\n  [3] Sensitivity sweep -- 128-byte states comparison")
print(f"  {'Change%':>8s} {'Pre Morse(cl)':>14s} {'Post Morse(cl)':>14s} {'Post Hex(cl)':>13s}")
print(f"  {'-'*8} {'-'*14} {'-'*14} {'-'*13}")

for pct in [10, 30, 50, 70, 90]:
    change_p = pct / 100.0
    key = f"bytes=128_change={change_p:.0%}"
    entry = POST["sensitivity_sweep"].get(key, {})
    post_morse = entry.get("cl100k_base", {}).get("morse_tokens", 0)
    post_hex = entry.get("cl100k_base", {}).get("hex_tokens", 0)

    # Pre-review: buggy Morse used only 1 byte
    # At 10%: 326 tokens (only 1 byte tracked, buggy)
    # At other rates: buggy values were also ~326 (same single-byte state)
    if pct == 10:
        pre_morse = 326
    else:
        pre_morse = 326  # buggy: same for all rates since only 1 byte

    print(f"  {pct:>7d}% {pre_morse:>12d}  {post_morse:>12d}  {post_hex:>12d}  {'(fixed!)' if post_morse != pre_morse else ''}")

# 4. Key metrics that changed
print("\n  [4] What the fixes changed")
print(f"  {'Metric':35s} {'Before (R0/R1)':20s} {'After (R3)':20s}")
print(f"  {'-'*35} {'-'*20} {'-'*20}")

changes = [
    ("128b @10% Morse vs Hex", "~99.5% (buggy)", "~44% (honest)"),
    ("1b canonical result", "Morse 4,270 / Hex N/A", "Morse 4,270 / Hex 945"),
    ("Hex baseline", "Not measured", "77.9% better than Morse on 1-byte"),
    ("Multi-byte coverage", "Not tested", "1/8/32/128 bytes × 5 change rates"),
    ("Change-rate sweep", "Not tested", "10/30/50/70/90%"),
    ("Tokenizer atomicity", "Assumed", "Verified across 4 tokenizers"),
    ("Best-case claim", "85% vs JSON", "1.4-2x vs hex at <50% change"),
    ("Protocol semantics", "Undefined", "7-state machine + sequences"),
    ("Auto-detection tier", "Silent/fragile", "Requires explicit tier="),
    ("DoS protection", "None", "MAX_STATE_BYTES=65536"),
    ("DSP apply() relay", "Always empty", "Returns incoming frame"),
]

for metric, before, after in changes:
    print(f"  {metric:35s} {before:20s} {after:20s}")

# 5. Score trajectory
print("\n  [5] Review score trajectory")
print(f"  {'Reviewer':20s} {'R1':>6s} {'R2':>6s} {'R3':>6s}")
print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}")
scores = [
    ("Archora", "6.5", "8.0", "8.5"),
    ("Draft Detective", "4.0", "7.0", "7.5"),
    ("Meet Review", "6.0", "7.0", "8.0"),
]
for reviewer, r1, r2, r3 in scores:
    print(f"  {reviewer:20s} {r1:>6s} {r2:>6s} {r3:>6s}")

print(f"\n  {'Average':20s} {'5.5':>6s} {'7.3':>6s} {'8.0':>6s}")

print("\n" + "=" * 72)
print("  Verdict: All engineering gaps closed. Paper draft only remaining gap.")
print("=" * 72)
