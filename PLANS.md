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

### Token Cost (measured, 500 ticks, 8-byte state, 25% change, cl100k_base)

| Mode | Total tokens | vs PM-1 alone |
|------|-------------|---------------|
| PM-1 Morse | ~6,100 | baseline |
| Braille (no ext, framed) | ~6,000 | ~2% better |
| Braille (with ext, framed) | ~3,000 | ~51% better |

The "without ext" case is roughly a wash — Braille's per-cell density (1 cell/byte vs 8 chars) offsets the tokenizer fragmentation even on stock tokenizers at this change rate. The load-bearing case for the upgrade is not "avoiding AB-1-without-ext losses" (those don't exist at this rate) but the **2× improvement on the with-ext path**. The handshake exists to maintain the universal bootstrap guarantee (PM-1 always works first), not to prevent a phantom regression.

### Risks

- **AB-1 dependency.** `HybridEncoder` implements Braille encoding as pure arithmetic (`0x2800 + byte`). No external AB-1 package required. True AB-1 compatibility (tokenizer extension check, command tier routing) would need an optional `ab1` extra but is deferred — arithmetic path covers 95% of use cases.
- **Tokenizer extension detection.** The agent admin configures `braille` capability per-deployment. No auto-detection. If unsure, don't advertise it.
