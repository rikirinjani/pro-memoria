# Implementation Plans

## Plan 1: Dual-Mode Encoding (PM-1 + AB-1 Hybrid)

### Status

| Component | Status |
|-----------|--------|
| Encoding constants (`protocol.py`) | Done |
| Handshake commands (`ENCODING`/`ENCODING_ACK`) | Done |
| `HybridEncoder` class (`hybrid.py`) | Done |
| HybridEncoder tests (9/9 pass, `test_hybrid.py`) | Done |
| Paper Discussion §5.3 hybrid subsection | Done |

### Remaining

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 1 | Wire `HybridEncoder` into `dsp.py` — `DiffState.diff()` and `DiffState.apply()` must call `enc.encode_byte()` / `enc.decode_char()` instead of hardcoded Morse. Add `encoding` param to `DiffState.__init__()`. | `dsp.py`, `hybrid.py` | Small |
| 2 | Wire `HybridEncoder` into `adapter.py` — `trace_to_state()` → `FailsafePM1.encode_state()` should use the negotiated encoding. Add `encoding` param to `PM1Session.__init__()`. | `adapter.py`, `hybrid.py` | Small |
| 3 | Wire `HybridEncoder` into `cli.py` — `pm1-trace trace --encoding braille` flag. Defaults to Morse. | `cli.py` | Tiny |
| 4 | Implement full handshake with encoding negotiation — `HybridHandshake` class that sends `ENCODING`, waits for `ENCODING_ACK`, selects encoding, transitions to SYNCING. | new file `handshake.py` | Medium |
| 5 | Integration test: start two `HybridEncoder` instances, run full handshake (HELLO → VERSION → ENCODING → ENCODING_ACK → ACK → SYNC → DATA), verify encoding is Braille when both sides support it, Morse when one side doesn't. | `test_hybrid.py` or new `test_handshake.py` | Medium |
| 6 | Integration test: encode a real self-harness trace through the full Braille path, verify roundtrip through `FailsafePM1`. | `verify_integration.py` | Small |
| 7 | Update `FailsafePM1` to accept encoding param so Hamming protect/verify uses correct byte representation. | `failsafe.py` | Small |
| 8 | Update paper §2 (Related Work) to cite `HYBRID_ENCODING.md` design and note the synergy as explicit contribution. | `paper/pro-memoria.md` | Tiny |

### Architecture

```
Agent A                           Agent B
  │                                 │
  │  HELLO (PM-1 Morse)             │  ← Always PM-1 (guaranteed to work)
  │──────────────────────────────>  │
  │  VERSION                        │
  │<──────────────────────────────> │
  │  ENCODING {morse, braille}      │
  │──────────────────────────────>  │
  │  ENCODING_ACK braille           │  ← Upgrade if both sides can
  │<──────────────────────────────  │
  │  ACK                            │
  │──────────────────────────────>  │
  │  SYNC (now in Braille)          │  ← All subsequent bytes use
  │<──────────────────────────────> │     HybridEncoder.encode_byte()
  │  DATA (Braille diffs)           │
  │──────────────────────────────>  │
```

On error recovery (`ERROR → RECOVERY → RESET`): `enc.reset()` to Morse, re-negotiate encoding in handshake.

### Token Cost

| Wiring | Per-byte | Per-tick (2 bytes) | Session (500 ticks) |
|--------|----------|-------------------|-------------------|
| PM-1 only | 8 tok | ~10 tok | ~5,000 tok |
| PM-1 → AB-1 | 1 tok | ~8 tok | ~4,000 tok (-20%) |
| AB-1 without ext | 3 tok | ~12 tok | ~6,000 tok (+20%) |

### Risks

- **AB-1 dependency.** `HybridEncoder` currently implements Braille encoding as pure arithmetic (`0x2800 + byte`). This does NOT require the AB-1 package. However, for true AB-1 compatibility (command tier routing, tokenizer extension check), an optional `ab1` extra dependency may be needed. Low risk — the arithmetic path covers 95% of use cases.
- **Tokenizer extension detection.** How does `ENCODING` know whether Braille cells are atomic? Answer: it doesn't — the agent admin knows. The flag is configured per-deployment, not auto-detected. If unsure, don't advertise `braille`.
