"""Pro Memoria — Real Agent Trace Benchmark.

Uses actual self-harness session traces (258 trace files) as the state
dataset instead of synthetic or AB-1 Crucible data.

Compares: JSON vs Hex vs Base64 vs Morse (raw) vs Morse (DSP) vs Braille (DSP)
across real agent state changes observed in production.

Tokenizer: cl100k_base (GPT-4), o200k_base (Claude)
"""

import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
AB1_REPO = HERE.parent / "ab1_repo"
TRACES_DIR = Path.home() / "self-harness" / "traces"

sys.path.insert(0, str(AB1_REPO))
sys.path.insert(0, str(HERE.parent))

from core import bits_to_morse, encode_bytes
from dsp import DiffState

RESULTS.mkdir(exist_ok=True)

import tiktoken

ENCODINGS = {
    "cl100k_base": tiktoken.get_encoding("cl100k_base"),
    "o200k_base": tiktoken.get_encoding("o200k_base"),
}


def count(text: str, enc_name: str) -> int:
    return len(ENCODINGS[enc_name].encode(text))


# ── Agent state model (8 bits per trace) ──────────────────────────────

AGENT_MAP = {
    "orchestrator": 0, "general": 1, "platform": 2, "fixer": 3,
    "explorer": 4, "oracle": 5, "librarian": 6, "coordinator": 7,
    "benchmark-runner": 8, "other": 15,
}

OUTCOME_MAP = {"pass": 0, "fail": 1, "partial": 2, "unknown": 3}

SEVERITY_MAP = {"none": 0, "low": 1, "medium": 2, "high": 3}


def trace_to_state(trace: dict, failures: dict) -> bytes:
    """Encode a real trace as an 8-byte agent state vector.

    Byte 0: agent type (0-15)
    Byte 1: outcome (0-3)
    Byte 2: duration bucket (0=0s, 1=<60s, 2=<300s, 3=<900s, 4=<3600s, 5=>=3600s)
    Byte 3: tool_calls bucket (0=0, 1=<10, 2=<30, 3=<100, 4=<300, 5=>=300)
    Byte 4: key_files count bucket (0=0, 1=<5, 2=<15, 4=<50, 4>=50)
    Byte 5: failure category (0=none, 1=tool, 2=config, 3=workflow, 4=process, 5=communication, 6=research, 7=other)
    Byte 6: failure severity (0-3)
    Byte 7: reserved (0 or 1 if validation present)
    """
    def bucket(value, ranges):
        for i, threshold in enumerate(ranges):
            if value < threshold:
                return i
        return len(ranges)

    agent_name = trace.get("agent", "other").lower()
    agent_byte = AGENT_MAP.get(agent_name, 15)

    outcome = trace.get("outcome", "unknown").lower()
    outcome_byte = OUTCOME_MAP.get(outcome, 3)

    dur = trace.get("duration_s", 0) or 0
    dur_byte = bucket(dur, [1, 60, 300, 900, 3600])

    tc = trace.get("tool_calls", 0) or 0
    tc_byte = bucket(tc, [1, 10, 30, 100, 300])

    kf = trace.get("key_files", []) or []
    kf_byte = bucket(len(kf), [1, 5, 15, 50])

    trace_id = trace.get("trace_id", "")
    fail = failures.get(trace_id, {})
    if fail:
        cat = fail.get("category", "other").lower()
        cat_map = {
            "tool": 1, "config": 2, "workflow": 3, "process": 4,
            "communication": 5, "research": 6, "other": 7,
        }
        fail_byte = cat_map.get(cat, 7)
        sev = fail.get("severity", "none").lower()
        sev_byte = SEVERITY_MAP.get(sev, 0)
    else:
        fail_byte = 0
        sev_byte = 0

    val_byte = 1 if trace.get("validation") else 0

    return bytes([
        agent_byte & 0xFF, outcome_byte & 0xFF, dur_byte & 0xFF,
        tc_byte & 0xFF, kf_byte & 0xFF, fail_byte & 0xFF,
        sev_byte & 0xFF, val_byte & 0xFF,
    ])


def _extract_trace(data: dict) -> dict | None:
    """Extract a trace dict from .json or .pm1 payload."""
    if "pm1_version" in data:
        # .pm1 file: extract trace metadata from top-level fields
        return {
            "agent": data.get("agent", "other"),
            "outcome": data.get("outcome", "unknown"),
            "duration_s": data.get("duration_s", 0),
            "tool_calls": data.get("tool_calls", 0),
            "key_files": data.get("key_files", []),
            "failure": data.get("failure", {}),
            "validation": True,
            "trace_id": data.get("session_id", data.get("slug", "?")),
        }
    # .json file: use as-is
    return data


def load_traces():
    """Load all real self-harness traces and failure records."""
    traces = []
    files = sorted(TRACES_DIR.glob("*.json")) + sorted(TRACES_DIR.glob("*.pm1"))
    for f in files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                data = json.load(fh)
            trace = _extract_trace(data)
            if trace is not None:
                traces.append(trace)
        except (json.JSONDecodeError, OSError):
            continue

    failures = {}
    fail_dir = Path.home() / "self-harness" / "failures"
    if fail_dir.exists():
        for f in sorted(fail_dir.glob("*.json")):
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    data = json.load(fh)
                failures[data.get("trace_id", "")] = data
            except (json.JSONDecodeError, OSError):
                continue

    return traces, failures


# ── Encoding formats ──────────────────────────────────────────────────

def encode_json(traces, failures):
    """Full JSON encoding (verbose baseline)."""
    parts = []
    for t in traces:
        tid = t.get("trace_id", "")
        fail = failures.get(tid, {})
        entry = {
            "agent": t.get("agent", ""),
            "outcome": t.get("outcome", ""),
            "duration": t.get("duration_s", 0),
            "tools": t.get("tool_calls", 0),
            "files": len(t.get("key_files", [])),
            "fail_cat": fail.get("category", "none") if fail else "none",
            "fail_sev": fail.get("severity", "none") if fail else "none",
        }
        parts.append(json.dumps(entry, separators=(",", ":")))
    return "\n".join(parts)


def encode_json_delta(traces, failures):
    """Delta-encoded JSON (steelman baseline)."""
    parts = []
    prev = None
    for t in traces:
        tid = t.get("trace_id", "")
        fail = failures.get(tid, {})
        entry = {
            "agent": t.get("agent", ""),
            "outcome": t.get("outcome", ""),
            "duration": t.get("duration_s", 0),
            "tools": t.get("tool_calls", 0),
            "files": len(t.get("key_files", [])),
            "fail_cat": fail.get("category", "none") if fail else "none",
            "fail_sev": fail.get("severity", "none") if fail else "none",
        }
        if entry != prev:
            parts.append(json.dumps(entry, separators=(",", ":")))
            prev = entry
    return "\n".join(parts)


def encode_hex(states):
    return "".join(s.hex() for s in states)


def encode_b64(states):
    return base64.b64encode(b"".join(states)).decode()


def encode_morse_raw(states):
    return "".join(encode_bytes(s) for s in states)


def encode_morse_dsp(states):
    ds = DiffState()
    parts = []
    prev = None
    for s in states:
        if s != prev:
            parts.append(ds.diff(s))
            prev = s
    return "".join(parts)


def encode_braille_dsp(states):
    try:
        from ab1 import State, encode_stream
        braille_states = []
        for s in states:
            for byte_val in s:
                braille_states.append(State.from_mask(byte_val & 0xFF))
        result, stats = encode_stream(braille_states)
        return result
    except Exception:
        return "[AB-1 not available]"


def encode_codebook(states):
    """Codebook compression: map each unique 8-byte state to a 1-byte index.

    Wire format: [4-byte N(codebook)] + [N*8 bytes codebook] + [N(indices) bytes indices]
    Then Base64-encoded for fair comparison (ASCII-safe, portable).
    """
    import struct
    unique = {}
    indices = bytearray()
    for s in states:
        if s not in unique:
            unique[s] = len(unique)
        indices.append(unique[s])
    codebook = bytearray()
    for s in sorted(unique, key=lambda x: unique[x]):
        codebook.extend(s)
    n = len(unique)
    header = struct.pack("<I", n)
    payload = bytes(header) + bytes(codebook) + bytes(indices)
    return base64.b64encode(payload).decode()


def run():
    print("=" * 68)
    print("  Pro Memoria -- Real Agent Trace Benchmark")
    print(f"  Dataset: {TRACES_DIR}")
    print("=" * 68)

    traces, failures = load_traces()
    n_traces = len(traces)
    n_failures = len(failures)
    print(f"\n  Loaded: {n_traces} traces, {n_failures} failure records")

    states = [trace_to_state(t, failures) for t in traces]
    n_unique = len(set(states))
    changes = sum(1 for i in range(1, len(states)) if states[i] != states[i-1])
    change_rate = changes / max(len(states) - 1, 1)
    print(f"  States: {n_traces} ({n_unique} unique), change rate: {change_rate:.1%}")
    print(f"  State width: 8 bytes per trace")

    s_json = encode_json(traces, failures)
    s_json_d = encode_json_delta(traces, failures)
    s_hex = encode_hex(states)
    s_b64 = encode_b64(states)
    s_morse = encode_morse_raw(states)
    s_morse_dsp = encode_morse_dsp(states)
    s_braille = encode_braille_dsp(states)

    print(f"\n  {'Format':22s} {'Chars':>8s} {'cl100k':>8s} {'o200k':>8s}")
    print(f"  {'-'*22} {'-'*8} {'-'*8} {'-'*8}")

    s_codebook = encode_codebook(states)

    formats = [
        ("Full JSON", s_json),
        ("Delta JSON (steelman)", s_json_d),
        ("Hex", s_hex),
        ("Base64", s_b64),
        ("Codebook", s_codebook),
        ("Morse (raw)", s_morse),
        ("Morse (DSP)", s_morse_dsp),
    ]
    if "[AB-1" not in s_braille:
        formats.append(("Braille (DSP)", s_braille))

    tok_results = {}
    for name, text in formats:
        chars = len(text)
        ct = count(text, "cl100k_base")
        ot = count(text, "o200k_base")
        tok_results[name] = {"chars": chars, "cl100k": ct, "o200k": ot}
        print(f"  {name:22s} {chars:>8d} {ct:>8d} {ot:>8d}")

    steel = tok_results["Delta JSON (steelman)"]["cl100k"]
    morse = tok_results["Morse (DSP)"]["cl100k"]
    print(f"\n  Savings vs Delta-JSON (cl100k_base):")
    for name, tr in tok_results.items():
        if name == "Delta JSON (steelman)":
            continue
        pct = round(100 * (1 - tr["cl100k"] / steel), 1)
        note = ""
        if name == "Morse (DSP)":
            note = "<-- PM-1"
        elif name == "Braille (DSP)":
            note = "<-- AB-1"
        elif name == "Codebook":
            note = "dictionary approach"
        elif name in ("Hex", "Base64"):
            note = "ASCII baseline"
        print(f"    {name:22s} {pct:>+6.1f}% {note}")

    out = {
        "dataset": "self-harness real traces",
        "n_traces": n_traces,
        "n_failures": n_failures,
        "n_unique_states": n_unique,
        "change_rate": round(change_rate, 4),
        "state_width_bytes": 8,
        "formats": tok_results,
    }
    out_file = RESULTS / "real_traces.json"
    out_file.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n  Results saved: {out_file}")


if __name__ == "__main__":
    run()