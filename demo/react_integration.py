"""Pro Memoria — Real-World ReAct Integration Demo.

Demonstrates PM-1 protocol in an actual agent handoff scenario using
real self-harness trace data. Simulates orchestrator -> fixer -> oracle
handoff cycle with PM-1 state encoding.

Shows:
1. Agent state serialized as PM-1 Morse frames
2. ReAct-style observe -> think -> act -> handoff loop
3. Token savings at each handoff boundary
4. Real failure recovery using Hamming error correction
"""

import argparse
import io
import json
import sys
from pathlib import Path

# Ensure UTF-8 output for emoji support on all platforms
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
elif hasattr(sys.stdout, "detach"):
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding="utf-8", line_buffering=True)

MORSE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MORSE_ROOT))

from core import bits_to_morse, morse_to_bits, encode_bytes, decode_bytes
from dsp import DiffState, encode_diff, decode_diff
from lexicon import hamming_encode, hamming_decode, parity_encode, parity_decode, bits_to_morse as lex_morse

# ── Optional: tiktoken token counting ──────────────────────────────────

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens using tiktoken. Returns 0 if tiktoken is unavailable."""
    if not HAS_TIKTOKEN:
        return 0
    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode(text))


def json_state(state: "AgentState") -> str:
    """Serialize AgentState as compact JSON (same format as PMHandoff.send)."""
    return json.dumps({
        "agent": state.agent_id,
        "phase": state.phase,
        "confidence": state.confidence,
        "errors": state.error_count,
        "tools": state.data[4],
        "files": state.data[5],
        "outcome": state.outcome,
        "flags": state.flags,
    }, separators=(",", ":"))

TRACES_DIR = Path.home() / "self-harness" / "traces"
FAILURES_DIR = Path.home() / "self-harness" / "failures"


# ── Agent State Model ─────────────────────────────────────────────────

class AgentState:
    """8-byte agent state for ReAct handoff.

    Byte 0: agent_id (0-15)
    Byte 1: phase (0=observe, 1=think, 2=act, 3=handoff)
    Byte 2: confidence (0=none, 1=low, 2=medium, 3=high)
    Byte 3: error_count (0-255)
    Byte 4: tool_calls_made (0-255)
    Byte 5: files_touched (0-255)
    Byte 6: outcome (0=running, 1=success, 2=fail, 3=retry)
    Byte 7: flags (bit0=has_errors, bit1=needs_review, bit2=escalated, bit3-7=0)
    """

    def __init__(self, agent_id=0, phase=0, confidence=0, error_count=0,
                 tool_calls=0, files_touched=0, outcome=0, flags=0):
        self.data = bytes([
            agent_id & 0xFF, phase & 0xFF, confidence & 0xFF,
            error_count & 0xFF, tool_calls & 0xFF, files_touched & 0xFF,
            outcome & 0xFF, flags & 0xFF,
        ])

    @classmethod
    def from_bytes(cls, data: bytes):
        assert len(data) == 8
        obj = cls.__new__(cls)
        obj.data = data
        return obj

    @property
    def agent_id(self): return self.data[0]
    @property
    def phase(self): return self.data[1]
    @property
    def confidence(self): return self.data[2]
    @property
    def error_count(self): return self.data[3]
    @property
    def outcome(self): return self.data[6]
    @property
    def flags(self): return self.data[7]

    def __eq__(self, other):
        return self.data == other.data

    def __repr__(self):
        phases = ["OBSERVE", "THINK", "ACT", "HANDOFF"]
        outcomes = ["RUNNING", "SUCCESS", "FAIL", "RETRY"]
        agents = {0: "orchestrator", 1: "fixer", 2: "oracle",
                  3: "explorer", 4: "librarian"}
        agent = agents.get(self.agent_id, f"agent_{self.agent_id}")
        return (f"<{agent} phase={phases[self.phase]} "
                f"conf={self.confidence} errors={self.error_count} "
                f"outcome={outcomes[self.outcome]}>")


# ── PM-1 Handoff Protocol ──────────────────────────────────────────────

class PMHandoff:
    """Simulates agent-to-agent handoff using PM-1 DSP protocol.

    Sender encodes state change as Morse DSP frame.
    Receiver decodes and applies.
    """

    def __init__(self):
        self.sender_state = DiffState()
        self.receiver_state = DiffState()
        self.frames_sent = []
        self.frames_received = []
        self.total_chars = 0
        self.json_chars = 0
        self.step_results = []  # list of dicts: label, pm1_chars, json_chars, tokens*

    def send(self, new_state: AgentState, label: str = ""):
        """Sender encodes state delta and transmits."""
        frame = self.sender_state.diff(new_state.data)
        self.frames_sent.append(frame)
        self.total_chars += len(frame)

        json_equiv = json_state(new_state)
        self.json_chars += len(json_equiv)

        # Capture per-step data for summary table
        step = {"label": label, "pm1_chars": len(frame), "json_chars": len(json_equiv)}
        if HAS_TIKTOKEN:
            step["pm1_tok_cl100k"] = count_tokens(frame)
            step["json_tok_cl100k"] = count_tokens(json_equiv)
            step["pm1_tok_o200k"] = count_tokens(frame, "o200k_base")
            step["json_tok_o200k"] = count_tokens(json_equiv, "o200k_base")
        self.step_results.append(step)

        if frame:
            print(f"  [{label}] SENT: {frame[:60]}{'...' if len(frame)>60 else ''}")
            print(f"           JSON: {json_equiv}")
            print(f"           PM-1: {len(frame)} chars  |  JSON: {len(json_equiv)} chars  "
                  f"  |  Savings: {100*(1-len(frame)/max(len(json_equiv),1)):.0f}%")
        else:
            print(f"  [{label}] (no state change — skipped)")

    def receive(self):
        """Receiver applies all pending frames."""
        for frame in self.frames_sent[len(self.frames_received):]:
            self.receiver_state.apply(frame)
            self.frames_received.append(frame)


# ── Simulated ReAct Loop ────────────────────────────────────────────────

def simulate_react_loop():
    """Run a realistic ReAct handoff cycle using real trace scenarios."""

    print("=" * 68)
    print("  🧠 Pro Memoria — ReAct Integration Demo")
    print("  Based on real self-harness agent handoff scenarios")
    print("=" * 68)

    handoff = PMHandoff()

    # Scenario 1: Orchestrator -> Fixer (bug fix task)
    print("\n  --- Scenario 1: Orchestrator delegates bug fix to Fixer ---\n")

    init = AgentState(agent_id=0, phase=0, confidence=2,
                      tool_calls=5, files_touched=3, outcome=0)
    handoff.send(init, "INIT")

    # Orchestrator observes, identifies bug
    obs = AgentState(agent_id=0, phase=0, confidence=2,
                     tool_calls=6, files_touched=3, outcome=0,
                     flags=0b00000001)
    handoff.send(obs, "OBSERVE")

    # Orchestrator thinks, plans handoff
    think = AgentState(agent_id=0, phase=1, confidence=3,
                       tool_calls=7, files_touched=3, outcome=0,
                       flags=0b00000001)
    handoff.send(think, "THINK")

    # Handoff to Fixer
    ho = AgentState(agent_id=1, phase=0, confidence=3,
                    tool_calls=0, files_touched=3, outcome=0,
                    flags=0b00000001)
    handoff.send(ho, "HANDOFF->FIXER")

    # Fixer acts, encounters error
    act1 = AgentState(agent_id=1, phase=2, confidence=2,
                      error_count=1, tool_calls=3, files_touched=4,
                      outcome=0, flags=0b00000001)
    handoff.send(act1, "FIXER-ACT-1")

    # Fixer retries
    act2 = AgentState(agent_id=1, phase=2, confidence=2,
                      error_count=1, tool_calls=5, files_touched=5,
                      outcome=3, flags=0b00000001)
    handoff.send(act2, "FIXER-RETRY")

    # Fixer succeeds
    done = AgentState(agent_id=1, phase=2, confidence=3,
                      error_count=1, tool_calls=8, files_touched=5,
                      outcome=1, flags=0)
    handoff.send(done, "FIXER-DONE")

    # Scenario 2: Fixer -> Oracle (review needed)
    print("\n  --- Scenario 2: Fixer escalates to Oracle for review ---\n")

    esc = AgentState(agent_id=2, phase=0, confidence=3,
                     tool_calls=0, files_touched=5, outcome=0,
                     flags=0b00000011)
    handoff.send(esc, "HANDOFF->ORACLE")

    # Oracle reviews, finds issue
    review = AgentState(agent_id=2, phase=0, confidence=2,
                        tool_calls=3, files_touched=5, outcome=0,
                        flags=0b00000011)
    handoff.send(review, "ORACLE-REVIEW")

    # Oracle approves
    approve = AgentState(agent_id=2, phase=1, confidence=3,
                         tool_calls=4, files_touched=5, outcome=1,
                         flags=0b00000010)
    handoff.send(approve, "ORACLE-APPROVE")

    # Final state reconciliation
    handoff.receive()
    final = AgentState.from_bytes(handoff.receiver_state.state)
    print(f"\n  Receiver final state: {final}")
    print(f"  Sender   final state: {AgentState.from_bytes(handoff.sender_state.state)}")
    print(f"  Match: {handoff.sender_state.state == handoff.receiver_state.state}")

    # Summary
    print(f"\n  {'='*55}")
    print(f"  📊 Pro Memoria vs JSON — Per-Step Breakdown")
    print(f"  {'='*55}")
    print(f"  | {'Step':<20} | {'PM-1':>7} | {'JSON':>7} | {'Saved':>6} | {'%':>7} |")
    print(f"  | {'-'*20} | {'-'*7} | {'-'*7} | {'-'*6} | {'-'*7} |")

    pm1_total = 0
    json_total = 0
    for step in handoff.step_results:
        pm1_c = step["pm1_chars"]
        json_c = step["json_chars"]
        if pm1_c == 0:
            continue
        pm1_total += pm1_c
        json_total += json_c
        saved = json_c - pm1_c
        pct = 100 * saved / max(json_c, 1)
        print(f"  | {step['label']:<20} | {pm1_c:>7} | {json_c:>7} | {saved:>6} | {pct:>6.1f}% |")

    total_saved = json_total - pm1_total
    total_pct = 100 * total_saved / max(json_total, 1)
    print(f"  | {'-'*20} | {'-'*7} | {'-'*7} | {'-'*6} | {'-'*7} |")
    print(f"  | {'TOTAL':<20} | {pm1_total:>7,} | {json_total:>7,} | {total_saved:>6,} | {total_pct:>6.1f}% |")

    # Token savings (if tiktoken available)
    if HAS_TIKTOKEN:
        print()
        print(f"  | {'Token encoding':<20} | {'PM-1':>7} | {'JSON':>7} | {'Saved':>6} | {'%':>7} |")
        print(f"  | {'-'*20} | {'-'*7} | {'-'*7} | {'-'*6} | {'-'*7} |")
        for enc_name, key_p, key_j in [("cl100k_base", "pm1_tok_cl100k", "json_tok_cl100k"),
                                        ("o200k_base", "pm1_tok_o200k", "json_tok_o200k")]:
            pm1_tok = sum(s.get(key_p, 0) for s in handoff.step_results)
            json_tok = sum(s.get(key_j, 0) for s in handoff.step_results)
            if pm1_tok == 0 and json_tok == 0:
                continue
            tok_saved = json_tok - pm1_tok
            tok_pct = 100 * tok_saved / max(json_tok, 1)
            print(f"  | {enc_name:<20} | {pm1_tok:>7} | {json_tok:>7} | {tok_saved:>6} | {tok_pct:>6.1f}% |")

    skipped = len([f for f in handoff.frames_sent if not f])
    if skipped:
        print(f"\n  (⏭ skipped {skipped} no-op frame{'' if skipped==1 else 's'})")

    # Hamming error correction demo
    print(f"\n  {'='*50}")
    print(f"  🔧 Hamming Error Correction Demo (real failure scenario)")
    print(f"  {'='*50}\n")

    # Simulate: Fixer sends DATA command (0x06) but bit gets flipped
    cmd = hamming_encode(0x06)  # DATA
    morse_cmd = bits_to_morse(cmd)
    print(f"  Original:  DATA (0x{cmd:02X}) -> {morse_cmd}")

    # Flip bit 3 (single-bit error during transit)
    corrupted = cmd ^ (1 << 3)
    morse_corrupt = bits_to_morse(corrupted)
    print(f"  Corrupted: bit 3 flipped -> 0x{corrupted:02X} -> {morse_corrupt}")

    # Decode with correction
    decoded, corrected, bad = hamming_decode(corrupted)
    cmd_name = {0x06: "DATA"}.get(decoded, f"0x{decoded:X}")
    print(f"  Decoded:   {cmd_name} (corrected={corrected}, uncorrectable={bad})")
    print(f"  Result:    {'PASS - error corrected' if corrected and not bad else 'FAIL'}")

    # Now simulate a double-bit error (uncorrectable)
    corrupted2 = cmd ^ (1 << 2) ^ (1 << 5)
    morse_corrupt2 = bits_to_morse(corrupted2)
    print(f"\n  Double error: bits 2,5 flipped -> 0x{corrupted2:02X} -> {morse_corrupt2}")
    decoded2, corrected2, bad2 = hamming_decode(corrupted2)
    print(f"  Decoded:     corrected={corrected2}, uncorrectable={bad2}")
    print(f"  Result:      {'DETECTED - double error flagged' if bad2 else 'UNDETECTED - silent corruption!'}")


# ── Comparison Mode ────────────────────────────────────────────────────

def run_comparison(quiet: bool = False):
    """Run PM-1 vs naive JSON-full-state comparison, printing a side-by-side table.

    When quiet=True, only the comparison table is printed (for CI/automation).
    """
    steps = [
        ("INIT", AgentState(agent_id=0, phase=0, confidence=2, tool_calls=5, files_touched=3, outcome=0)),
        ("OBSERVE", AgentState(agent_id=0, phase=0, confidence=2, tool_calls=6, files_touched=3, outcome=0, flags=0b00000001)),
        ("THINK", AgentState(agent_id=0, phase=1, confidence=3, tool_calls=7, files_touched=3, outcome=0, flags=0b00000001)),
        ("HANDOFF->FIXER", AgentState(agent_id=1, phase=0, confidence=3, tool_calls=0, files_touched=3, outcome=0, flags=0b00000001)),
        ("FIXER-ACT-1", AgentState(agent_id=1, phase=2, confidence=2, error_count=1, tool_calls=3, files_touched=4, outcome=0, flags=0b00000001)),
        ("FIXER-RETRY", AgentState(agent_id=1, phase=2, confidence=2, error_count=1, tool_calls=5, files_touched=5, outcome=3, flags=0b00000001)),
        ("FIXER-DONE", AgentState(agent_id=1, phase=2, confidence=3, error_count=1, tool_calls=8, files_touched=5, outcome=1, flags=0)),
        ("HANDOFF->ORACLE", AgentState(agent_id=2, phase=0, confidence=3, tool_calls=0, files_touched=5, outcome=0, flags=0b00000011)),
        ("ORACLE-REVIEW", AgentState(agent_id=2, phase=0, confidence=2, tool_calls=3, files_touched=5, outcome=0, flags=0b00000011)),
        ("ORACLE-APPROVE", AgentState(agent_id=2, phase=1, confidence=3, tool_calls=4, files_touched=5, outcome=1, flags=0b00000010)),
    ]

    # ── Pass 1: PM-1 differential encoding ──
    if not quiet:
        print("=" * 60)
        print("  🔵 Pass 1: PM-1 (differential encoding via DiffState)")
        print("=" * 60)

    pm1_handoff = PMHandoff()
    for label, state in steps:
        frame = pm1_handoff.sender_state.diff(state.data)
        pm1_handoff.frames_sent.append(frame)
        pm1_handoff.total_chars += len(frame)
        json_equiv = json_state(state)
        pm1_handoff.json_chars += len(json_equiv)
        step = {"label": label, "pm1_chars": len(frame), "json_chars": len(json_equiv)}
        if HAS_TIKTOKEN:
            step["pm1_tok_cl100k"] = count_tokens(frame)
            step["json_tok_cl100k"] = count_tokens(json_equiv)
            step["pm1_tok_o200k"] = count_tokens(frame, "o200k_base")
            step["json_tok_o200k"] = count_tokens(json_equiv, "o200k_base")
        pm1_handoff.step_results.append(step)
        if not quiet and frame:
            print(f"  [{label}] PM-1 frame: {len(frame):>4} chars  |  JSON equiv: {len(json_equiv):>4} chars")

    # ── Pass 2: Naive JSON full state each step ──
    if not quiet:
        print()
        print("=" * 60)
        print("  🟡 Pass 2: Naive JSON (full state each step)")
        print("=" * 60)

    json_full_steps = []
    json_full_total = 0
    for label, state in steps:
        serialized = json_state(state)
        json_full_steps.append(len(serialized))
        json_full_total += len(serialized)
        if not quiet:
            print(f"  [{label}] JSON full: {len(serialized):>4} chars")

    # ── Comparison Table ──
    print()
    print("=" * 65)
    print("  📊 PM-1 vs JSON — Side-by-Side Comparison")
    print("=" * 65)
    print(f"  | {'Step':<20} | {'PM-1 Δ':>7} | {'JSON full':>9} | {'Saved':>6} | {'%':>7} |")
    print(f"  | {'-'*20} | {'-'*7} | {'-'*9} | {'-'*6} | {'-'*7} |")

    pm1_total = 0
    json_equiv_total = 0
    for i, step in enumerate(pm1_handoff.step_results):
        pm1_c = step["pm1_chars"]
        json_c = step["json_chars"]
        json_full_c = json_full_steps[i]
        if pm1_c == 0:
            continue
        pm1_total += pm1_c
        json_equiv_total += json_full_c
        saved = json_full_c - pm1_c
        pct = 100 * saved / max(json_full_c, 1)
        print(f"  | {step['label']:<20} | {pm1_c:>7} | {json_full_c:>9} | {saved:>6} | {pct:>6.1f}% |")

    total_saved = json_equiv_total - pm1_total
    total_pct = 100 * total_saved / max(json_equiv_total, 1)
    print(f"  | {'-'*20} | {'-'*7} | {'-'*9} | {'-'*6} | {'-'*7} |")
    print(f"  | {'TOTAL':<20} | {pm1_total:>7,} | {json_equiv_total:>9,} | {total_saved:>6,} | {total_pct:>6.1f}% |")

    # Token comparison
    if HAS_TIKTOKEN:
        print()
        print(f"  | {'Token encoding':<20} | {'PM-1':>7} | {'JSON':>9} | {'Saved':>6} | {'%':>7} |")
        print(f"  | {'-'*20} | {'-'*7} | {'-'*9} | {'-'*6} | {'-'*7} |")
        for enc_name, key_p, key_j in [("cl100k_base", "pm1_tok_cl100k", "json_tok_cl100k"),
                                        ("o200k_base", "pm1_tok_o200k", "json_tok_o200k")]:
            pm1_tok = sum(s.get(key_p, 0) for s in pm1_handoff.step_results)
            json_tok_sum = 0
            for s, state in zip(pm1_handoff.step_results, steps):
                json_full = json_state(state[1])
                json_tok_sum += count_tokens(json_full, enc_name)
            if pm1_tok == 0 and json_tok_sum == 0:
                continue
            tok_saved = json_tok_sum - pm1_tok
            tok_pct = 100 * tok_saved / max(json_tok_sum, 1)
            print(f"  | {enc_name:<20} | {pm1_tok:>7} | {json_tok_sum:>9} | {tok_saved:>6} | {tok_pct:>6.1f}% |")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pro Memoria — PM-1 vs JSON bandwidth comparison demo",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Run PM-1 and JSON-full-state passes side-by-side with comparison table",
    )
    parser.add_argument(
        "--json-vs-pm1", action="store_true",
        help="Print ONLY the comparison table (silent mode, for CI/automation)",
    )
    args = parser.parse_args()

    if args.json_vs_pm1:
        run_comparison(quiet=True)
    elif args.compare:
        run_comparison(quiet=False)
    else:
        simulate_react_loop()