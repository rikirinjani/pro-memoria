# Pro Memoria Protocol Specification

> Draft. Normative specification — this document defines what "Pro Memoria" is.
> The reference implementation lives in `core.py`, `dsp.py`, `lexicon.py`.

## 1. Scope

Pro Memoria (PM) defines a canonical, deterministic protocol for representing and exchanging
agent state across heterogeneous LLM environments. It is not a compression format. It is not a
serialization library. It is a protocol family with one reference encoding (PM-1) and a
stable set of invariants that any alternate encoding must satisfy.

## 2. Protocol invariants

Every valid PM encoding SHALL satisfy the following invariants. These are verifiable by the
reference test suite in `core.py:invariant_check()`.

| # | Property | What it means | Test |
|---|----------|----------------|------|
| I1 | **ASCII-only** | Every symbol in the PM alphabet is ASCII (0x00–0x7F). | `ord(c) <= 127` |
| I2 | **Normalization-safe** | Every symbol is NFC and NFKC invariant — Unicode normalization does not change the symbol. | `unicodedata.normalize("NFC", c) == c` |
| I3 | **Bijective** | Encoding is roundtrip-safe: `decode(encode(byte)) == byte` for all 256 values. | `roundtrip_check()` |
| I4 | **Deterministic** | Same input always produces the same output. No randomness, no timestamp injection, no locale-dependence. | Property of the algorithm |
| I5 | **Tokenizer-independent** | Token count is predictable and independent of the LLM tokenizer used; symbols are atomic in all known tokenizers. | Verified in `bench/token_efficiency.py` |

Invariants are **enforceable**, not aspirational. If a new encoding is proposed, it must pass
the invariant test suite before being called a PM encoding. If a future edit to the PM-1
reference implementation adds a symbol that fails I2, the test suite catches it.

## 3. State model

The abstract PM state model is a **fixed-width byte vector**. A "state" is any contiguous
sequence of bytes. A "transition" is the difference between two consecutive states.

The reference implementation uses an 8-byte state vector mapping to agent telemetry fields
(agent ID, phase, confidence, error count, tool calls, files touched, outcome, flags).
But the protocol itself does not mandate any particular byte count or field mapping —
those are application-level conventions.

## 4. PM-1: Canonical ASCII encoding

PM-1 is the reference wire encoding of the Pro Memoria protocol.

### 4.1 Alphabet

```
. = 0
- = 1
```

Two characters. Both ASCII. Both atomic (1 token each) in all known tokenizers
(cl100k_base, o200k_base, p50k_base, r50k_base — verified).

### 4.2 Byte encoding

Each byte is encoded as 8 characters, MSB first:

```
byte → 8 bits → 8 chars
0x41 → 01000001 → .-.....-
```

### 4.3 Encoding function

```
bits_to_morse(b: int) → str       # 0 ≤ b ≤ 255
morse_to_bits(s: str) → int       # len(s) == 8
```

### 4.4 Multi-byte encoding

```
encode_bytes(data: bytes) → str   # length = 8 × len(data)
decode_bytes(s: str) → bytes      # length must be multiple of 8
```

## 5. Differential State Protocol

The Differential State Protocol (DSP) emits only bytes that changed since the last state
vector.

### 5.1 Diff format

```
index:byte_value|index:byte_value|...
```

- `index` — 0-based byte offset
- `byte_value` — 8-character PM-1 encoded byte
- `|` — frame separator

Example:

```
State A: [0x41, 0x42, 0x00, 0x00]
State B: [0x41, 0xFF, 0x00, 0x00]
Diff:    "1:--------|"
```

Only byte 1 changed (0x42 → 0xFF). Bytes 0, 2, 3 are unchanged — not transmitted.

### 5.2 Behavior guarantees

- **Grow support**: If the new state is longer than the old state, the diff includes new bytes.
- **Shrink support**: If the new state is shorter, the old state is used as baseline for
  the out-of-range bytes (they're treated as present-but-unchanged in the old state, so
  the shrunk state is reconstructed correctly).
- **Initial state**: First diff emits the entire initial vector (all bytes are "changed"
  from the zero state).
- **Maximum state size**: Configurable limit (default 64KB) — DoS guard against
  unbounded state expansion.

### 5.3 DSP vs the invariant list

DSP is an **optional optimization** layered on top of PM-1. A PM-1 encoding without DSP
is still valid PM. DSP satisfies all five invariants because it only manipulates the
content of the encoded stream, not the alphabet or the encoding rules.

## 6. Error detection and correction

PM-1 supports two tiers of error protection:

### 6.1 Hamming [8,4,4]

16 protected commands. Each 4-bit command is encoded as 8 Hamming bits.
Properties:
- Single-bit error: **corrected**
- Double-bit error: **detected** (uncorrectable flag raised)
- Syndrome table: 16 syndromes → 16 correction vectors

### 6.2 Parity check

128 commands with single-bit parity protection.
Properties:
- Single-bit error: **detected** (not corrected)
- Double-bit error: undetected

### 6.3 Command routing

Commands occupy byte values 0x00–0x0F (Hamming-protected) and 0x10–0x1F (parity-protected).
The remaining 224 byte values (0x20–0xFF) are available for state data. Tier routing is
explicit — commands and data cannot collide.

## 7. Negotiation

### 7.1 Encoding negotiation

PM-1 supports negotiated encoding upgrades:

```
HELLO (PM-1 Morse)           →  Always PM-1 (guaranteed to work)
VERSION                       →  Capability exchange
ENCODING {morse, braille}     →  Advertise supported encodings
ENCODING_ACK braille          →  Upgrade if both sides support
```

On error recovery (`ERROR → RECOVERY → RESET`): negotiation resets to PM-1 Morse
as the safe fallback.

### 7.2 Handshake state machine

7 states define the connection lifecycle:

| State | Meaning |
|-------|---------|
| CLOSED | No connection |
| HANDSHAKE | Version and encoding negotiation (HELLO, VERSION, ENCODING, ENCODING_ACK) |
| SYNCING | State synchronization after handshake or recovery |
| DATA | Normal operation — DSP frames carrying state diffs |
| ERROR | Recoverable error detected |
| RECOVERY | Re-synchronizing after error (RETRY, RESET, STATE_REP, ACK) |
| DISCONNECT | Clean shutdown |

Handshake timeout: configurable. Error recovery path: `ERROR → RECOVERY → CLOSED → HANDSHAKE → SYNCING → DATA`. On error, negotiation resets to PM-1 Morse as the safe fallback.

## 8. Separation of concerns

Pro Memoria separates these concerns, and no layer SHALL depend on the implementation
details of another:

```
PM-S (Symbolic)    —  Authoring notation, human-facing, compiles to PM-1
    ↓ compile only (one-directional)
PM-1 (Canonical)   —  Wire encoding, the only format agents transmit
    ↓
PM-View            —  Rendering, human-facing, display-only
                      NEVER parsed back into PM-1
```

Key constraint: **PM-View has no code path that feeds into PM-1.** The rendered form
is equivalent to syntax highlighting — it is presentation, not data. This is a
security boundary, not a convention.

## 9. Security considerations

- **Unicode normalization attack**: PM-1's alphabet avoids this by constraining to
  ASCII-only and verifying I2 at test time. A future encoding that adds non-ASCII
  symbols must pass the invariant suite or be rejected.
- **State size DoS**: Maximum state size limit (default 64KB) in DSP prevents
  unbounded expansion attacks.
- **Replay attacks**: PM-1 does not include nonce/timestamp in the encoded frame.
  Session-level replay protection is an application-level concern.

## 10. Reference test vectors

Any conforming PM-1 implementation MUST produce these outputs:

```python
# Byte encoding
bits_to_morse(0x41) == '.-.....-'
bits_to_morse(0xC0) == '--......'
bits_to_morse(0x00) == '........'
bits_to_morse(0xFF) == '--------'

# Roundtrip
morse_to_bits('.-.....-') == 65
morse_to_bits('--------') == 255

# Multi-byte
encode_bytes(b'Hi') == '.-..-....--.-..-'
decode_bytes('.-..-....--.-..-') == b'Hi'
```

## 11. License

- Specification: CC-BY-4.0
- Reference implementation: Apache-2.0
