# Pro Memoria

**Single-agent state telemetry protocol.** Encodes 8-bit binary state as ASCII Morse (`.` for 0, `-` for 1) with differential emission, Hamming error correction, and handshake recovery. ~85% token savings vs delta-JSON on its design target.

`Pro Memoria` (Latin: *"for memory"*) is **not** a general log compressor — it's for **single-agent evolving state** where change between ticks is small and infrequent. Use it for agent session resume, cross-model handoff, pipe-safe agent communication, long-running monitors, and low-power edge agents. For multi-agent task logs (discrete unrelated events), use codebook or Base64 instead.

---

## Design Philosophy: Pro Memoria vs Shorthand

Pro memoria — "for memory" in Latin. Skip the routine, mark the transition.

| Theater Rehearsal | Agent Session |
|---|---|
| "We'll do the anthem here" (skips singing) | `⠇` (skips verbose state JSON) |
| Only rehearse scene transitions | Only emit state changes |
| Everyone knows the routine | System knows the encoding |
| Saves 2 hours of rehearsal time | Saves 92% of state-tracking tokens |
| Focus on the tricky parts | Focus compute on actual work |

**Pro memoria is not shorthand.** Shorthand compresses content. Pro memoria eliminates **content that doesn't need to be spoken** because everyone already knows it. The routine is the encoding. Only the transitions are worth transmitting.

---

## When to use PM-1

| ✅ Use it for | ❌ Not for |
|---|---|
| Single agent state, tick-by-tick | Multi-agent task/event logs |
| <15% change rate between ticks | >50% change rate (discrete events) |
| Session resume / cross-model handoff | General-purpose data compression |
| Pipe-safe communication (plain ASCII) | When every last token matters (Base64 wins at high change) |
| Lossy channels needing error correction | Where simpler formats are sufficient |

**Classic pattern:** An agent runs for 200 steps, state shifts gradually (priority, mode, context). PM-1 emits only the transitions — 60–85% fewer tokens than delta-JSON — and Hamming code catches any corruption between steps.

---

## Inspiration

Pro Memoria is directly inspired by **Agent Braille (AB-1)** by [Tetrahedroned](https://github.com/Tetrahedroned/Agent-Braille), which encodes 8-bit agency state as single Unicode Braille cells (U+2800–U+28FF). AB-1's core ideas — the orthogonal 8-dimensional state model, the differential state protocol (emit-on-change), and the Hamming [8,4,4] error-correcting code — are adapted here with a different encoding layer.

The key insight of Pro Memoria is that ASCII `.` and `-` are **unconditionally 1 token per character** in every tokenizer (`cl100k_base`, `o200k_base`, `p50k_base`, `r50k_base` — all verified). This removes AB-1's dependency on registering Unicode Braille cells as single tokens via tokenizer extension. The tradeoff is density: Braille fits in 1 Unicode cell/state (~1–3 tokens), while Morse requires 8 ASCII chars/state (~8 tokens).

**Attribution:** Pro Memoria's Differential State Protocol (DSP), Hamming [8,4,4] math, and benchmark methodology are adapted from AB-1's published design (Apache-2.0 / CC-BY-4.0). The encoding scheme (`.`/`-` bits), zero-setup analysis, and protocol state machine are new contributions.

---

## Repository

- **GitHub:** https://github.com/rikirinjani/pro-memoria
- **Reference:** [Tetrahedroned/Agent-Braille](https://github.com/Tetrahedroned/Agent-Braille) — the work that inspired this project

---

## Project Structure

```
morse/
├── core.py           Phase 1: bits <-> Morse encoding (256 byte roundtrip)
├── dsp.py            Phase 2: Differential State Protocol (DiffState, emit-on-change)
├── lexicon.py        Phase 3: Hamming [8,4,4] commands + parity-protected tier
├── protocol.py       Phase 3b: Protocol state machine (7 states, handshake, error recovery)
├── bench/
│   ├── token_efficiency.py   Multi-axis benchmark (hex, Base64, Morse, AB-1, JSON)
│   ├── test_dsp.py           58 DSP edge-case tests
│   └── pre_vs_post_comparison.py  Pre-review vs post-review comparison
├── redteam/
│   └── pro-memoria.md        Peer review artifacts (3 rounds)
└── paper/                     (placeholder for manuscript)
```

---

## Quick Start

```python
from core import bits_to_morse, morse_to_bits
from dsp import DiffState

# Encode a byte
morse = bits_to_morse(0x41)   # '.-.....-'
byte = morse_to_bits(morse)   # 65

# Track state changes
ds = DiffState()
ds.diff(b'\x41\x42')          # '0:.-.....-|1:.-....-.|'
ds.diff(b'\x41\xFF')          # '1:--------|'
```

---

## Benchmark Results

### Real agent traces (237 traces, 106 unique states, 82.6% change rate, cl100k_base)

| Format | Tokens | vs Delta-JSON |
|--------|--------|---------------|
| Delta JSON (steelman) | 7,290 | baseline |
| **Codebook** | **750** | **+89.7%** dictionary approach |
| **Base64** | **1,153** | **+84.2%** ASCII baseline |
| Hex | 1,297 | +82.2% |
| Morse (raw) | 2,175 | +70.2% |
| Braille (DSP) | 2,297 | +68.5% (all 8 bytes) |
| **Morse (DSP)** | **2,880** | **+60.5%** PM-1 |

Morse DSP is optimized for **low-change-rate agent-state monitoring** (<15% change), where synthetic sweeps show ~70% savings over hex. Real self-harness traces (82.6% change rate) represent **discrete task-completion events** — consecutive rows are different subagents, not a single evolving state. Codebook compression exploits the limited unique-state palette (106/237) and wins on this data shape.

### Synthetic: AB-1 Crucible low-change trace (1,417 states, 7% change rate, cl100k_base)

| Format | Tokens | vs Steelman JSON |
|--------|--------|-----------------|
| Steelman JSON | 28,076 | baseline |
| **Morse DSP** | **4,270** | **84.8% savings** |
| Hex | 945 | 77.9% *more* tokens than Morse |

See full sensitivity sweep in `bench/token_efficiency.py`.

**ECC overhead.** Above numbers are raw Morse (no error correction). With Hamming [8,4,4] enabled, each 8-byte state becomes 16 Hamming-protected bytes before Morse encoding — roughly doubling token cost. Use ECC for checkpoint/session-resume (low frequency, high stakes). Skip it for high-frequency intra-session ticks where a bad tick is overwritten by the next one anyway.

---

## License

- **Code:** Apache-2.0
- **Specification:** CC-BY-4.0

(Consistent with AB-1's licensing conventions.)
