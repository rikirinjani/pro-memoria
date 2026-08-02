"""PM-1 Self-Evaluation Loop — runs on Mac Mini with Bonsai 27B.

Generates PM-1 traces, sends each to Bonsai for critique via its
reasoning stream, and stores evaluation results. Designed to run
independently on Mac Mini; Windows can be off.

Bonsai 27B outputs thinking/reasoning before content (~3000 tok
reasoning at 13 tok/s = ~4 min). This loop handles that by parsing
scores from the reasoning text and storing raw responses.

Usage:
    source venv/bin/activate
    python bench/loop_eval.py [--count N]

Output:
    bench/results/eval_{timestamp}/
        trace_N.pm1            — generated PM-1 trace
        trace_N_eval.json      — Bonsai raw response + parsed score
        summary.json           — aggregate results
"""

import json
import re
import sys
import time
import random
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))

from opencode_plugin.adapter import trace_to_state
from opencode_plugin.failsafe import FailsafePM1

# ── Config ──────────────────────────────────────────────────────────────

BONSAI_URL = "http://localhost:8080/v1"
MODEL = "/Users/ptpakdefarma/models/ternary-bonsai-27b"
OUTPUT_DIR = HERE / "results"
N_TRACES = 3           # default (each takes ~4-5 min with Bonsai)
SLEEP_BETWEEN = 5      # seconds between API calls

# ── Helpers ─────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_trace(seed: int) -> dict:
    """Generate a plausible PM-1 trace with random multi-state data."""
    rng = random.Random(seed)
    n_states = rng.randint(2, 6)
    states = []
    prev = 0
    for i in range(n_states):
        data_len = rng.randint(20, 60)
        data = bytes([rng.randint(0, 255) for _ in range(data_len)])
        value = rng.randint(0, 2**64 - 1)
        states.append({
            "index": i,
            "value": value,
            "delta_from_prev": value ^ prev if i > 0 else 0,
            "data_bytes": len(data),
            "data_hex": data.hex()[:32] + "..." if len(data) > 16 else data.hex(),
        })
        prev = value

    return {
        "agent": "loop_eval",
        "outcome": rng.choice(["pass", "pass", "pass", "pass", "fail"]),
        "duration_s": rng.randint(10, 600),
        "tool_calls": rng.randint(1, 25),
        "key_files": [f"/path/to/file_{rng.randint(1,5)}.py"],
        "action": f"Generated state trace iteration {seed}",
        "n_states": n_states,
        "states": states,
        "seed": seed,
    }


def encode_to_pm1(trace: dict, slug: str) -> tuple[str, dict]:
    """Encode a trace dict to PM-1 format, return (encoded_str, payload)."""
    state = trace_to_state(trace)
    fs = FailsafePM1(session_id=slug, encoding="morse")
    encoded = fs.encode(state)

    payload = {
        "pm1_version": 1,
        "session_id": slug,
        "timestamp": trace.get("timestamp", now_iso()),
        "agent": trace.get("agent", "loop_eval"),
        "outcome": trace.get("outcome", "pass"),
        "duration_s": trace.get("duration_s", 0),
        "tool_calls": trace.get("tool_calls", 0),
        "encoding": "morse",
        "n_states": 1,
        "state_width": 8,
        "failsafe": fs.stats(),
        "pm1": encoded,
        "action": trace.get("action", ""),
    }
    return encoded, payload


def extract_score(text: str) -> int | None:
    """Extract a 1-10 quality score from Bonsai's reasoning text."""
    # Priority 1: explicit quality/score patterns
    for pat in [
        r'(?:quality|score|rating)\s*(?::|is|=|was)\s*([89]|10|[1-7])\b',
        r'rate[ds]?\s+(?:it|this|the\s+trace)\s+(?:as\s+)?([89]|10|[1-7])\b',
        r'overall\s+(?:score|quality|rating)[^0-9]*([89]|10|[1-7])\b',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return int(m.group(1))

    # Priority 2: "X/10" pattern
    m = re.search(r'([89]|10|[1-7])\s*/\s*10', text)
    if m:
        return int(m.group(1))

    # Priority 3: last standalone number 1-10 near "quality" or "score"
    candidates = re.findall(r'(?:quality|score|rating).{0,40}?([89]|10|[1-7])\b', text, re.IGNORECASE)
    if candidates:
        return int(candidates[-1])

    return None


def query_bonsai(prompt: str) -> dict:
    """Send prompt to Bonsai, return structured response."""
    import urllib.request

    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4000,
    }).encode()

    req = urllib.request.Request(
        f"{BONSAI_URL}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def critique_with_bonsai(payload: dict) -> dict:
    """Send PM-1 trace to Bonsai 27B for evaluation. Return parsed result."""
    pm1_text = payload.get("pm1", "")
    agent = payload.get("agent", "?")
    outcome = payload.get("outcome", "?")
    action = payload.get("action", "?")
    pm1_chars = len(pm1_text)
    pm1_tok = pm1_chars * 0.125

    prompt = (
        f"PM-1 trace review.\n"
        f"Agent={agent} Outcome={outcome} Action={action}\n"
        f"Payload: {pm1_chars} Morse chars (~{pm1_tok:.0f} tokens)\n\n"
        f"Questions:\n"
        f"1. Is this trace plausible? (yes/no)\n"
        f"2. Quality score 1-10 (10=excellent)\n"
        f"3. Brief suggestion for improvement\n\n"
        f"Start with SCORE: X where X is 1-10."
    )

    try:
        result = query_bonsai(prompt)
        msg = result["choices"][0].get("message", {})
        content = msg.get("content", "")
        reasoning = msg.get("reasoning", "")
        finish = result["choices"][0]["finish_reason"]

        combined = (content or "") + " " + (reasoning or "")
        score = extract_score(combined)

        # Also try to find plausible yes/no
        plausible = None
        pm = re.search(r'plausible[^.]*?(yes|no)', combined, re.IGNORECASE)
        if pm:
            plausible = pm.group(1).lower() == "yes"

        return {
            "score": score,
            "plausible": plausible,
            "content_preview": (content or reasoning or "")[:500],
            "reasoning_len": len(reasoning or ""),
            "content_len": len(content or ""),
            "finish_reason": finish,
            "bonsai_model": MODEL,
            "bonsai_timestamp": now_iso(),
        }

    except Exception as e:
        return {
            "error": str(e),
            "score": None,
            "bonsai_timestamp": now_iso(),
        }


def run_all(count: int):
    """Generate N traces, critique each, save results."""
    timestamp = now_iso().replace(":", "-").split(".")[0]
    run_dir = OUTPUT_DIR / f"eval_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print("PM-1 Self-Evaluation Loop (Bonsai 27B)")
    print(f"  Traces:  {count}")
    print(f"  Bonsai:  {BONSAI_URL}")
    print(f"  Output:  {run_dir}")
    print(f"  Note:    Each eval takes ~4-5 min (Bonsai reasoning at 13 tok/s)")
    print()

    all_results = []
    est_total = 0

    for i in range(count):
        slug = f"loop-eval-{timestamp}-{i:03d}"
        print(f"[{i+1}/{count}] Generating trace {slug}...")

        trace = generate_trace(seed=int(time.time()) + i)
        encoded, payload = encode_to_pm1(trace, slug)

        trace_path = run_dir / f"trace_{i:03d}.pm1"
        with open(trace_path, "w") as f:
            json.dump(payload, f, indent=2)

        pm1_chars = len(encoded)
        print(f"  Encoded: {pm1_chars} Morse chars ({pm1_chars * 0.125:.0f} tok)")

        print(f"  Bonsai critique (this will take ~4 min)...")
        t0 = time.time()
        eval_result = critique_with_bonsai(payload)
        elapsed = time.time() - t0

        eval_path = run_dir / f"trace_{i:03d}_eval.json"
        with open(eval_path, "w") as f:
            json.dump(eval_result, f, indent=2)

        score = eval_result.get("score", "?")
        plausible = eval_result.get("plausible", "?")
        print(f"  Score: {score}/10 | Plausible: {plausible} | Took: {elapsed:.0f}s")

        all_results.append({
            "trace": slug,
            "pm1_chars": pm1_chars,
            "pm1_tokens": pm1_chars * 0.125,
            "evaluation": eval_result,
        })

        est_total += elapsed
        if i < count - 1:
            remaining = (count - i - 1) * (est_total / (i + 1))
            print(f"  Est. remaining: {remaining:.0f}s")
            time.sleep(SLEEP_BETWEEN)

    # ── Summary ────────────────────────────────────────────────
    scores = []
    plausibles = 0
    total_plaus = 0
    for r in all_results:
        ev = r["evaluation"]
        s = ev.get("score")
        if isinstance(s, (int, float)):
            scores.append(s)
        p = ev.get("plausible")
        if p is True:
            plausibles += 1
            total_plaus += 1
        elif p is False:
            total_plaus += 1

    summary = {
        "timestamp": timestamp,
        "n_traces": count,
        "bonsai_url": BONSAI_URL,
        "bonsai_model": MODEL,
        "total_pm1_chars": sum(r["pm1_chars"] for r in all_results),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "plausible_pct": round(100 * plausibles / total_plaus, 1) if total_plaus else None,
        "total_duration_s": round(sum(r["evaluation"].get("duration_s", 0) for r in all_results if "duration_s" not in r["evaluation"]), 1),
        "results": all_results,
    }

    summary_path = run_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print()
    print("Done. Results in:", run_dir)
    if summary["avg_score"] is not None:
        print(f"  Traces:    {count}")
        print(f"  Avg score: {summary['avg_score']}/10")
        print(f"  Range:     {summary['min_score']} – {summary['max_score']}")
        print(f"  Plausible: {summary['plausible_pct']}%")
    else:
        print("  No scores extracted. Check individual eval files.")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PM-1 Self-Evaluation Loop")
    parser.add_argument("--count", type=int, default=N_TRACES,
                        help="Number of traces (each takes ~4-5 min)")
    args = parser.parse_args()
    run_all(args.count)
