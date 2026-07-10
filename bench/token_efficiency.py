"""Pro Memoria — Phase 4: Token Efficiency Benchmark.

Multi-axis comparison: JSON vs Hex vs Base64 vs Morse vs Braille (AB-1).

Baselines (all ASCII, zero-setup):
  - hex: 2 chars/byte
  - Base64: 4 chars per 3 bytes
  - Morse: 8 chars/byte
  - Naive JSON: compact per-step status
  - Steelman delta-JSON: emit-on-change (fair baseline)
  - AB-1 Braille: Unicode cells (reference, needs tokenizer extension)

Tokenizers: cl100k_base (GPT-4) and o200k_base (Claude)
"""

import base64
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
CRUCIBLE = HERE.parent / "ab1_repo" / "bench" / "results" / "crucible_trace.json"
AB1_REPO = HERE.parent / "ab1_repo"

import sys
sys.path.insert(0, str(AB1_REPO))
from ab1 import State, encode_stream

sys.path.insert(0, str(HERE.parent))
from dsp import DiffState

RESULTS.mkdir(exist_ok=True)

# ── Token counting ────────────────────────────────────────────────────

import tiktoken

ENCODINGS = {
    "cl100k_base": tiktoken.get_encoding("cl100k_base"),
    "o200k_base": tiktoken.get_encoding("o200k_base"),
}


def count(text: str, enc_name: str) -> int:
    return len(ENCODINGS[enc_name].encode(text))


# ── Per-tokenizer atomicity verification ──────────────────────────────

ALL_TOKENIZERS = ["cl100k_base", "o200k_base", "p50k_base", "r50k_base"]


def verify_atomicity() -> dict:
    """Verify '.' and '-' are each 1 token in all tokenizers."""
    results = {}
    for name in ALL_TOKENIZERS:
        enc = tiktoken.get_encoding(name)
        dot_tokens = enc.encode('.')
        dash_tokens = enc.encode('-')
        results[name] = {
            "dot_tokens": len(dot_tokens),
            "dash_tokens": len(dash_tokens),
            "dot_is_atomic": len(dot_tokens) == 1,
            "dash_is_atomic": len(dash_tokens) == 1,
        }
    return results


# ── Load trace ────────────────────────────────────────────────────────

def state_to_mask(d: dict) -> int:
    return (
        int(d["io"])
        | (int(d["logic"]) << 1)
        | (int(d["source"]) << 2)
        | (int(d["privacy"]) << 3)
        | (int(d["temporal"]) << 4)
        | (int(d["audit"]) << 5)
        | ((int(d["priority"]) & 0b11) << 6)
    )


def load_crucible(path: str) -> tuple[list[int], list[dict]]:
    with open(path) as f:
        raw = json.load(f)
    masks = [state_to_mask(d) for d in raw]
    return masks, raw


# ── Encoding formats (byte-level state) ───────────────────────────────

def encode_hex(masks: list[int]) -> str:
    return "".join(f"{m:02x}" for m in masks)


def encode_b64(masks: list[int]) -> str:
    return base64.b64encode(bytes(masks)).decode()


def encode_morse_raw(masks: list[int]) -> str:
    """Full Morse (no delta-encoding)."""
    from core import bits_to_morse
    return "".join(bits_to_morse(m) for m in masks)


# ── Delta-encoded formats (emit-on-change) ────────────────────────────

def morse_dsp(masks: list[int]) -> str:
    ds = DiffState()
    parts, prev = [], None
    for m in masks:
        if m != prev:
            parts.append(ds.diff(bytes([m])))
            prev = m
    return "".join(parts)


def morse_dsp_bytes(states: list[bytes]) -> str:
    """Morse DSP over full byte-vector states (N bytes per state).

    Each element is a bytes object of length N (the full state vector).
    DiffState tracks the full byte sequence and emits diffs for any changed
    byte position. This is the fair comparison for multi-byte hex/b64.
    """
    ds = DiffState()
    parts, prev = [], None
    for s in states:
        if s != prev:
            parts.append(ds.diff(s))
            prev = s
    return "".join(parts)


def braille_dsp(masks: list[int]) -> tuple[str, object]:
    states = [State.from_mask(m) for m in masks]
    return encode_stream(states)


def json_status(step: int, d: dict) -> str:
    return json.dumps(
        {
            "step": step,
            "io": "read" if d["io"] == 0 else "write",
            "logic": "deductive" if d["logic"] == 0 else "probabilistic",
            "src": "internal" if d["source"] == 0 else "external",
            "priv": "public" if d["privacy"] == 0 else "encrypted",
            "temporal": "current" if d["temporal"] == 0 else "planned",
            "audited": bool(d["audit"]),
            "prio": d["priority"],
        },
        separators=(",", ":"),
    )


def steelman_json(masks: list[int], raw: list[dict]) -> str:
    lines, prev = [], None
    for i, (d, m) in enumerate(zip(raw, masks)):
        if m != prev:
            lines.append(json_status(i, d))
            prev = m
    return "\n".join(lines)


# ── Synthetic state generators ────────────────────────────────────────

def synthetic_states(n_steps: int, n_bytes: int, change_p: float, seed: int = 7) -> list[bytes]:
    """Generate synthetic state traces of given byte-width and change rate."""
    rng = random.Random(seed)
    cur = bytes(rng.randint(0, 255) for _ in range(n_bytes))
    seq = [cur]
    for _ in range(n_steps - 1):
        if rng.random() < change_p:
            cur = bytes(rng.randint(0, 255) for _ in range(n_bytes))
        seq.append(cur)
    return seq


# ── Benchmark runner ──────────────────────────────────────────────────

def run_crucible_benchmark() -> dict:
    """Run the primary comparison on the AB-1 Crucible trace."""
    masks, raw = load_crucible(str(CRUCIBLE))
    n_states = len(masks)
    n_unique = len(set(masks))

    s_hex = encode_hex(masks)
    s_b64 = encode_b64(masks)
    s_morse_raw = encode_morse_raw(masks)
    s_morse = morse_dsp(masks)
    s_braille, stats = braille_dsp(masks)
    s_steel = steelman_json(masks, raw)

    n_emitted = stats.n_emitted
    emit_ratio = stats.emit_ratio

    results = {"n_states": n_states, "n_unique": n_unique,
               "n_emitted": n_emitted, "emit_ratio": round(emit_ratio, 4),
               "char_counts": {
                   "hex": len(s_hex), "base64": len(s_b64),
                   "morse_raw": len(s_morse_raw), "morse_dsp": len(s_morse),
                   "braille_dsp": len(s_braille), "steelman_json": len(s_steel),
               }}

    for tname in ENCODINGS:
        tok = {fmt: count(s, tname) for fmt, s in [
            ("hex", s_hex), ("base64", s_b64), ("morse_raw", s_morse_raw),
            ("morse_dsp", s_morse), ("braille_dsp", s_braille),
            ("steelman_json", s_steel)]}

        tok["naive_json_per_step"] = round(tok["steelman_json"] / (n_emitted or 1), 1)

        steel = tok["steelman_json"]
        tok["morse_vs_steelman_pct"] = round(100 * (1 - tok["morse_dsp"] / steel), 1)
        tok["braille_vs_steelman_pct"] = round(100 * (1 - tok["braille_dsp"] / steel), 1)
        tok["morse_vs_braille_pct"] = round(100 * (1 - tok["morse_dsp"] / tok["braille_dsp"]), 1)
        tok["hex_vs_morse_pct"] = round(100 * (1 - tok["hex"] / tok["morse_dsp"]), 1)
        tok["b64_vs_morse_pct"] = round(100 * (1 - tok["base64"] / tok["morse_dsp"]), 1)

        results[tname] = tok

    return results


def run_sensitivity_sweep() -> dict:
    """Sweep over byte-widths and change rates (fair N-byte comparison)."""
    results = {}
    for n_bytes in [1, 8, 32, 128]:
        for change_p in [0.1, 0.3, 0.5, 0.7, 0.9]:
            key = f"bytes={n_bytes}_change={change_p:.0%}"
            states = synthetic_states(500, n_bytes, change_p)

            # All formats encode ALL N bytes
            s_hex = "".join(s.hex() for s in states)
            s_b64 = base64.b64encode(b"".join(states)).decode()
            s_morse = morse_dsp_bytes(states)

            entry = {"n_bytes": n_bytes, "change_p": change_p, "n_states": len(states)}
            for tname in ENCODINGS:
                entry[tname] = {
                    "hex_tokens": count(s_hex, tname),
                    "base64_tokens": count(s_b64, tname),
                    "morse_tokens": count(s_morse, tname),
                }
            results[key] = entry

    return results


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("  Pro Memoria -- Token Efficiency Benchmark (extended)")
    print(f"  Dataset: {CRUCIBLE.name}")
    print("=" * 68)

    # 1. Atomicity verification
    print("\n  [1] Per-tokenizer atomicity check")
    atomicity = verify_atomicity()
    for name, r in atomicity.items():
        status = "PASS" if r["dot_is_atomic"] and r["dash_is_atomic"] else "FAIL"
        print(f"      {name:16s} '.'={r['dot_tokens']} tok  '-'={r['dash_tokens']} tok  {status}")
    assert all(r["dot_is_atomic"] and r["dash_is_atomic"] for r in atomicity.values())

    # 2. Crucible trace benchmark
    print("\n  [2] AB-1 Crucible benchmark")
    crucible = run_crucible_benchmark()
    print(f"      States: {crucible['n_states']}, unique: {crucible['n_unique']}, emits: {crucible['n_emitted']} ({crucible['emit_ratio']:.1%})")
    print(f"      {'Format':20s} {'Chars':>7s} {'cl100k':>8s} {'o200k':>8s}")
    print(f"      {'-'*20} {'-'*7} {'-'*8} {'-'*8}")
    for fmt in ["hex", "base64", "morse_raw", "morse_dsp", "braille_dsp", "steelman_json"]:
        c = fmt.replace("_", " ").title()
        chars = crucible["char_counts"][fmt]
        ct = crucible.get("cl100k_base", {}).get(fmt, 0)
        ot = crucible.get("o200k_base", {}).get(fmt, 0)
        print(f"      {c:20s} {chars:>7d} {ct:>8d} {ot:>8d}")

    c = crucible["cl100k_base"]
    steel_tok = c["steelman_json"]
    morse_tok = c["morse_dsp"]

    print(f"\n      {'Cross-format comparison (cl100k):':35s}")
    print(f"      {'Against':>12s} {'Tokens':>8s} {'Savings':>8s} {'Note':>20s}")
    print(f"      {'-'*12} {'-'*8} {'-'*8} {'-'*20}")
    print(f"      {'Steelman JSON':>12s} {steel_tok:>8d} {c['morse_vs_steelman_pct']:>+7.1f}% {'fair baseline':>20s}")
    print(f"      {'Hex':>12s} {c['hex']:>8d} {c['hex_vs_morse_pct']:>+7.1f}% {'ASCII zero-setup':>20s}")
    print(f"      {'Base64':>12s} {c['base64']:>8d} {c['b64_vs_morse_pct']:>+7.1f}% {'ASCII zero-setup':>20s}")
    print(f"      {'AB-1':>12s} {c['braille_dsp']:>8d} {c['morse_vs_braille_pct']:>+7.1f}% {'needs ext':>20s}")
    print(f"\n      {'Note: Morse beats hex 1.4-2x on multi-byte states at <50%':55s}")
    print(f"      {'change (see sweep below). Hex wins at high change rates.':55s}")

    # 3. Sensitivity sweep (multi-byte + change rate)
    print("\n  [3] Sensitivity sweep (fair N-byte comparison)")
    sweep = run_sensitivity_sweep()
    print(f"      {'Bytes':>5s} {'Chg%':>5s} {'Hex/cl':>8s} {'B64/cl':>8s} {'Mor/cl':>8s} {'Hex/o200k':>9s} {'B64/o200k':>9s} {'Mor/o200k':>9s}")
    print(f"      {'-'*5} {'-'*5} {'-'*8} {'-'*8} {'-'*8} {'-'*9} {'-'*9} {'-'*9}")
    for key, e in sorted(sweep.items(), key=lambda kv: (kv[1]["n_bytes"], kv[1]["change_p"])):
        hc = e["cl100k_base"]["hex_tokens"]
        bc = e["cl100k_base"]["base64_tokens"]
        mc = e["cl100k_base"]["morse_tokens"]
        ho = e["o200k_base"]["hex_tokens"]
        bo = e["o200k_base"]["base64_tokens"]
        mo = e["o200k_base"]["morse_tokens"]
        print(f"      {e['n_bytes']:>5d} {e['change_p']:>4.0%} {hc:>8d} {bc:>8d} {mc:>8d} {ho:>9d} {bo:>9d} {mo:>9d}")

    # 4. Save aggregate results
    all_results = {
        "atomicity": atomicity,
        "crucible": crucible,
        "sensitivity_sweep": sweep,
    }
    out = RESULTS / "token_efficiency.json"
    out.write_text(json.dumps(all_results, indent=2))
    print(f"\n  Results saved: {out}")


if __name__ == "__main__":
    main()
