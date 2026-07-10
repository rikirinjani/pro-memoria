# Implementation Plans

## Plan 1: Dual-Mode Encoding (PM-1 + AB-1 Hybrid)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Wire `HybridEncoder` into `dsp.py` — `DiffState.diff()`/`apply()` use `enc.encode_byte()` | Done | `dsp.py`, `hybrid.py` |
| 2 | Wire `HybridEncoder` into `adapter.py` — `PM1Session.__init__(encoding=)` | Done | `adapter.py` |
| 3 | Wire `HybridEncoder` into `cli.py` — `--encoding braille` flag | Done | `cli.py` |
| 4 | Implement full handshake — `HybridHandshake` class | Done | `handshake.py` |
| 5 | Integration test: handshake + Braille roundtrip | Done | `test_handshake.py` (17/17) |
| 6 | Integration test: Braille through FailsafePM1 | Done | Covered in `test_handshake.py` |
| 7 | Update `FailsafePM1` to accept encoding param | Done | `failsafe.py` |
| 8 | Update paper §2 to cite hybrid encoding | Pending | `paper/pro-memoria.md` |
| 9 | Design philosophy: "skip what's known" table in README | Done | `README.md` |

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
