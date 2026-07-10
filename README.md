# Pro Memoria

**ASCII-native binary protocol for AI agent state communication.**

`Pro Memoria` (Latin: *"for memory"*) encodes 8-bit binary state as 8-character ASCII Morse strings (`.` for 0, `-` for 1), with differential state emission and optional error correction. ~85% token savings vs delta-JSON with **zero setup** — no Unicode, no tokenizer extension, no vocabulary changes.

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

## Benchmark Results (AB-1 Crucible trace, 1417 states, cl100k_base)

| Format | Tokens | vs Steelman JSON |
|--------|--------|-----------------|
| Steelman JSON | 28,076 | baseline |
| **Morse DSP** | **4,270** | **84.8% savings** |
| Hex | 945 | 77.9% *more* efficient than Morse |
| AB-1 Braille | 2,244 | 92.0% savings (needs tokenizer extension) |

Morse wins at ≤10% change rates on multi-byte states (1.4–2× fewer tokens than hex). Hex wins at high change rates. See full sensitivity sweep in `bench/token_efficiency.py`.

---

## License

- **Code:** Apache-2.0
- **Specification:** CC-BY-4.0

(Consistent with AB-1's licensing conventions.)
