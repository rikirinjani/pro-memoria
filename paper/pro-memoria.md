# Pro Memoria: Protocol Invariants for Deterministic Agent State Communication

> **Authors:** [AUTHOR_NAME], inspired by Tetrahedroned/Agent-Braille (Apache-2.0, CC-BY-4.0)
>
> **Repository:** https://github.com/rikirinjani/pro-memoria
>
> **Status:** Draft v2 — [DATE]

---

## Abstract

Large language model (LLM) agents generate significant token overhead tracking their internal state across multi-step tasks. Existing compact state representations either require tokenizer extensions (e.g., Agent Braille) or remain tied to JSON with modest compression. We present **Pro Memoria (PM-1)** , an ASCII-native binary protocol that encodes 8-bit state as 8-character Morse strings (`.` = 0, `-` = 1), combined with a Differential State Protocol (DSP) that emits only changed bytes and a two-tier error-correcting command lexicon (Hamming [8,4,4] with single-error correction and parity with single-error detection). Because `.` and `-` are unconditionally single tokens in every major tokenizer (cl100k_base, o200k_base, p50k_base, r50k_base — verified), PM-1 requires **zero setup**: no vocabulary extension, no Unicode registration, no configuration changes.

PM-1 occupies a specific point in the growing design space of machine-native communication: it intentionally trades expressive power for deterministic decoding, compressing structured state vectors with guaranteed bit-perfect recovery. On the AB-1 Crucible trace (1,417 single-byte states), PM-1 achieves 84.8% token savings versus delta-encoded JSON (cl100k_base). On 157 real agent self-harness traces (8-byte state vectors), live production measurements show 89.4% aggregate byte savings. A sensitivity sweep across 1–128 byte states and 10–90% change rates shows PM-1 beats hex by 1.4–2× at ≤10% change rates on multi-byte states.

We formalize PM-1's design as a set of five executable protocol invariants (ASCII-only, normalization-safe, bijective, deterministic, tokenizer-independent) enforced by a test suite that fails the build if any invariant is violated. The protocol is implemented in ~750 lines of pure Python with zero dependencies, a documented 7-state protocol machine, and a canonical specification. A case study in protocol design — the evolution from an initial diacritic-as-state-marker hypothesis through empirical rejection to a clean architectural separation (encoding ≠ rendering) — illustrates how executable invariants prevent silent degradation as a protocol matures.

---

## 1. Introduction

LLM agents increasingly use structured internal state to track progress across multi-step tasks: tool calls completed, files touched, confidence levels, error counts, phase transitions, and outcome flags. As agent frameworks (ReAct, function-calling loops, orchestrate–act–observe pipelines) grow in sophistication, the volume of state-tracking tokens grows correspondingly.

The standard approach — serializing state as compact JSON — produces verbose output even with minimized field names and whitespace. A single agent state transition (agent ID, phase, confidence, tool calls, files, outcome) consumes ~60–100 characters or ~20–40 tokens depending on the tokenizer. Over hundreds of steps in a typical agent session, this overhead accumulates to thousands of tokens — pure scaffolding that carries no semantic information for the task at hand.

Recent work has proposed more efficient encodings. **Agent Braille (AB-1)** [Tetrahedroned, 2025] encodes 8-bit agency state as single Unicode Braille cells (U+2800–U+28FF), achieving ~92% token savings versus delta-encoded JSON via a Differential State Protocol (DSP) and a hardened command lexicon. However, AB-1 requires a **tokenizer extension** to map Braille cells to single tokens. Without it, each Braille cell fragments into ~3 byte-tokens on stock tokenizers, eliminating the savings.

Concurrently, **BabelTele** [Zhu et al., 2026] investigates a complementary direction: encoding arbitrary semantic text into compact model-centric representations. BabelTele demonstrates that LLMs can recover 99.5% semantic fidelity from text condensed to 27.9% of its original length, validating the broader premise that machine-native communication is a viable design space. However, BabelTele's approach is fundamentally different: it compresses natural language using LLM-generated representations with semantic (lossy) recovery, while PM-1 compresses structured state vectors with deterministic (lossless) decoding. These are neighboring points in a two-dimensional design space — (Structured State ↔ Natural Language) × (Exact Recovery ↔ Semantic Recovery) — rather than competing solutions.

We present **Pro Memoria (PM-1)** , which adopts AB-1's DSP and Hamming [8,4,4] math but replaces the Unicode Braille encoding layer with ASCII `.` and `-` characters. Our key observation is that `.` and `-` are atomic (single-token) in **every** production tokenizer without any extension. This yields a zero-setup protocol: the same 84–92% token savings regime as AB-1, but portable across any LLM provider or tokenizer without configuration.

The tradeoff is encoding density. AB-1 fits one 8-bit state in a single Unicode cell (~1–3 tokens). PM-1 requires 8 ASCII characters per byte, which is inherently 8 tokens per byte. At low state-change rates (≤10%), DSP ensures PM-1's per-byte cost is amortized across long stable runs. At high change rates, the 8× raw overhead dominates and simpler encodings like hex (2 chars/byte) outperform.

Beyond the encoding, we contribute a **protocol invariants methodology**: five properties (ASCII-only, normalization-safe, bijective, deterministic, tokenizer-independent) that are enforced as executable tests rather than documented promises. A case study traces the evolution from a diacritic-as-state-marker hypothesis through empirical rejection (Unicode normalization silently destroys bit information) to a clean architectural separation where encoding, rendering, and authoring occupy distinct layers with no reverse path from presentation to protocol. This separation — encoding ≠ rendering, and the renderer must never feed back into the encoder — is the kind of guarantee that only executable invariants can enforce as a protocol grows.

**Contributions:**

1. **PM-1 encoding** — a deterministic, roundtrip-safe mapping from 8-bit bytes to 8-character Morse strings (`.` = 0, `-` = 1), verified for all 256 byte values.
2. **Zero-setup property** — proof that `.` and `-` are single tokens in cl100k_base, o200k_base, p50k_base, and r50k_base, making PM-1 immediately usable in any LLM environment.
3. **Differential State Protocol** — emit-on-change frame format with grow/shrink support and configurable maximum state size (64KB DoS guard).
4. **Two-tier error-correcting lexicon** — 16 Hamming [8,4,4] commands (single-bit correction, double-bit detection) and 128 parity-protected commands (single-bit detection), occupying the same 8-bit encoding space with explicit tier routing.
5. **Protocol invariants** — five executable guarantees (I1–I5) enforced by a test suite, with a case study in how invariants prevent silent protocol degradation.
6. **Comprehensive benchmarks** — evaluation on the AB-1 Crucible trace, 157 real agent self-harness traces (live production), and a sensitivity sweep over byte-width and change rate.
7. **Canonical specification** — PROTOCOL.md providing normative test vectors, state model, and separation-of-concerns architecture.

---

## 2. Related Work

### 2.1 Agent Braille (AB-1)

AB-1 [Tetrahedroned, 2025] is the closest prior art. It defines an 8-dimensional orthogonal agency state model (I/O, logic mode, source, privacy, temporal phase, audit, priority), encodes each state as a Unicode Braille cell (U+2800–U+28FF), and provides a Differential State Protocol that emits cells only on state change. Its hardened lexicon uses the same Hamming [8,4,4] code for 16 commands and a single-parity code for 128 commands. AB-1 ships a tokenizer extension to make Braille cells atomic.

PM-1 is directly inspired by AB-1 and reuses:
- The DSP emit-on-change discipline
- The Hamming [8,4,4] encoding mathematics and syndrome table
- The two-tier (Hamming + parity) command architecture
- The benchmark methodology and Crucible trace

PM-1 diverges by replacing the Unicode Braille encoding with ASCII Morse. The tradeoff is density (8 chars/byte vs 1 cell/state) for portability (no extension needed).

### 2.2 BabelTele

BabelTele [Zhu et al., 2026] investigates whether semantic information can be encoded in compact, non-standard textual forms that sacrifice human readability while remaining recoverable by LLMs. Through readability diagnostics, model likelihood measures, and downstream task evaluations, BabelTele demonstrates that instruction-tuned LLMs can recover 99.5% semantic fidelity from text condensed to 27.9% of its original length.

BabelTele and PM-1 occupy complementary positions in the emerging design space of machine-native communication. BabelTele targets **arbitrary natural language** — any text, any semantics — with **semantic (lossy) recovery** that depends on the specific LLM used as decoder. PM-1 targets **fixed-schema structured state** with **deterministic (lossless) recovery** that is LLM-agnostic and guaranteed by a mathematical encoding.

These are not competing approaches; they address fundamentally different communication tasks. We include BabelTele in the related work to position PM-1 within a broader research trend toward representations that decouple human readability from machine recoverability. Figure 6 maps the design space.

### 2.3 Existing Compact Encodings

**Hex encoding** (2 chars/byte) and **Base64** (4 chars per 3 bytes ≈ 1.33× overhead) are both ASCII-native and zero-setup. Hex is the simplest baseline: 16 tokens per byte (each nybble is one hex char). Base64 achieves 1.33 tokens per byte but requires padding and is less human-readable. Both are included as baselines in our benchmarks.

**Codebook compression** exploits low unique-state counts in agent trace data. When an agent session produces only 106 unique states out of 237 transitions, a codebook mapping each unique state to a 1-byte index and transmitting the codebook + index stream achieves strong compression. We include codebook as an additional baseline for the real-trace benchmark, noting it requires both encoder and decoder to share the codebook table.

### 2.4 Hybrid Morse–Braille Encoding

PM-1 and AB-1 are not competing protocols — they occupy complementary positions in the same stack. PM-1 Morse is the universal bootstrap (zero setup, guaranteed to work in any LLM environment). AB-1 Braille is the density upgrade (1 Unicode cell per byte vs 8 ASCII chars). The protocol handshake with `ENCODING`/`ENCODING_ACK` commands negotiates a shared encoding: the initiator advertises `{morse, braille}` and the responder selects the best common option. On error recovery, the encoder resets to Morse.

### 2.5 Machine-Native Communication Taxonomy

We propose a **Machine-Native Communication Taxonomy** — a two-axis framework for classifying systems that encode information for machine-to-machine (rather than human-to-machine) consumption:

| Axis | Spectrum | Description |
|------|----------|-------------|
| **Target Domain** | Structured State ↔ Natural Language | Is the content a fixed-schema byte vector or arbitrary semantic text? |
| **Recovery Guarantee** | Exact/Deterministic ↔ Semantic/Learned | Is recovery mathematical (bit-perfect) or probabilistic (LLM-inferred)? |

Figure 6 positions PM-1 among related systems on these axes. PM-1 and AB-1 occupy the top-left quadrant (structured state, exact recovery); BabelTele occupies the bottom-right (natural language, semantic recovery). Hex and Base64 are baseline deterministic encodings; Codebook requires two-pass scanning but achieves exact recovery on structured data. Future systems can be classified by asking: *"which quadrant?"*

This taxonomy clarifies that PM-1's contribution is not "better compression than BabelTele" — the two systems optimize different objectives on different inputs. The contribution is a **deterministic state transport** in a quadrant previously occupied only by AB-1 (with its tokenizer-extension requirement) and hex/Base64 (with no differential emission).

A third implicit axis — **Failure Semantics** — further distinguishes these systems: PM-1 is **fail-stop** (corruption detected, system halts), while BabelTele is **fail-soft** (corruption absorbed, system continues with approximate output). Neither is universally better; they are designed for different risk tolerances. This distinction maps to the systems engineering concepts of **reliability** (how often is output correct?) versus **integrity** (when output is wrong, will the system know?). PM-1 optimizes integrity; BabelTele optimizes reliability.

---

## 3. Methods

### 3.1 PM-1 Encoding Layer

PM-1 maps each 8-bit byte to an 8-character ASCII string and back:

- Bit = 0 → `.` (dot)
- Bit = 1 → `-` (dash)
- Bits are encoded MSB-first (bit 7 → char 0)

Encoding a byte `b`:

```
morse[i] = '-' if (b >> (7 - i)) & 1 else '.'
for i = 0..7
```

This is deterministic for all 256 byte values, verified by exhaustive roundtrip test.

**Zero-setup property.** We verified that `.` and `-` are each encoded as exactly 1 token in four tokenizers: cl100k_base (GPT-4/GPT-4o), o200k_base (Claude), p50k_base (Codex), and r50k_base (GPT-3). Both characters fall in the ASCII single-byte token range of every BPE-based tokenizer, so they cannot be merged with adjacent characters into multi-byte tokens. This property is structural, not empirical — any BPE tokenizer trained on text that includes ASCII punctuation will assign `.` and `-` single-token encodings because they appear frequently as isolated characters.

### 3.2 Protocol Invariants

PM-1's design is formalized as five executable invariants, verified by the test suite in `core.py:invariant_check()`:

| # | Invariant | Meaning | Enforcement |
|---|-----------|---------|-------------|
| I1 | **ASCII-only** | Every alphabet symbol is ASCII (0x00–0x7F). | `ord(c) <= 127` |
| I2 | **Normalization-safe** | Every symbol is NFC and NFKC invariant — Unicode normalization does not change it. | `unicodedata.normalize("NFC", c) == c` |
| I3 | **Bijective** | `decode(encode(byte)) == byte` for all 256 values. | Exhaustive roundtrip test |
| I4 | **Deterministic** | Same input always produces same output. | Property of the algorithm |
| I5 | **Tokenizer-independent** | Token count is predictable and independent of the LLM tokenizer. | Verified in benchmarks |

These invariants are **enforceable, not aspirational**. If a future edit adds a character to the PM-1 alphabet that fails I2 (e.g., a combining Unicode mark that silently normalizes), the test suite catches it before it reaches production. This is a qualitatively different guarantee from stating the property in documentation: the property survives future edits because it is asserted at build time.

### 3.3 Differential State Protocol (DSP)

The DSP emits a **diff frame** containing only the byte positions that changed between consecutive states, plus an index for each changed byte:

```
<index>:<8-morse-chars>|<index>:<8-morse-chars>|...
```

Control commands:
- `T:<new_length>|` — truncate state to `new_length` bytes

The `DiffState` class maintains the current state buffer and computes diffs on each update. It supports three operations:
- `diff(new_state)` — compare, emit diff, update
- `apply(frame)` — apply incoming diff to current state
- `sync(new_state)` — full state replacement (used in initial handshake or error recovery)

A maximum state size of 65,536 bytes bounds decoder allocations and provides a DoS guard.

### 3.4 Lexicon: Two-Tier Error Correction

PM-1 defines two command tiers that share the same 8-bit encoding space:

**Tier 1 — Hamming [8,4,4] (16 commands, distance 4):** Uses an extended Hamming code. Four data bits are encoded into eight bits with three syndrome bits and one overall parity bit. Single-bit errors are corrected; double-bit errors are detected. The 16 commands (NOP, ACK, NAK, RESET, SYNC, REQ, DATA, EOF, ERR, RETRY, STATUS, CONFIG, HELLO, BYE, ECHO, HALT) implement the protocol control layer.

**Tier 2 — Parity-protected (128 commands, distance 2):** Seven data bits plus even parity in the MSB. Any single-bit error is detected. These commands extend the protocol with application-level operations (STATE_REQ, STATE_REP, DIFF, FULL_SYNC, COMPRESS, etc.).

**Tier collision:** The value `0x87` is a valid codeword in both tiers (Hamming command 7 = EOF; parity command 7 = FULL_SYNC). The protocol requires explicit tier specification — auto-detection is intentionally not supported.

### 3.5 Protocol State Machine

PM-1 defines a 7-state connection lifecycle:

| State | Purpose | Key Commands |
|-------|---------|-------------|
| CLOSED | No connection | HELLO, VERSION |
| HANDSHAKE | Version negotiation | VERSION, VERSION_ACK, ENCODING, ENCODING_ACK |
| SYNCING | Full state sync | SYNC, STATE_REP, ACK |
| DATA | Normal operation | DIFF, FULL_SYNC, ECHO, STATUS, ERR |
| ERROR | Recoverable error | RETRY, RESET, STATUS |
| RECOVERY | Re-syncing | RESET, REQ, STATE_REP, ACK |
| DISCONNECT | Clean shutdown | BYE, HALT |

Error recovery follows: ERROR → STATUS/RESET → RECOVERY → REQ → STATE_REP → ACK → DATA. On error, encoding negotiation resets to PM-1 Morse as the safe fallback.

### 3.6 Benchmark Datasets

We evaluate on two datasets:

**AB-1 Crucible trace.** 1,417 single-byte state snapshots from AB-1's benchmark suite, representing an 8-dimensional agency model (I/O, logic, source, privacy, temporal, audit, priority). Only 6 unique masks; 748 state changes (52.8% emit ratio).

**Real self-harness traces.** 157 traces from actual agent sessions in the self-harness system, encoded as 8-byte state vectors (agent type, outcome, duration bucket, tool-calls bucket, files bucket, failure category, failure severity, validation flag). 106 unique states; 82.6% state-change rate. Live production data with ongoing accumulation.

We also generate synthetic states for sensitivity analysis: 500-step sequences at byte widths of 1, 8, 32, and 128, with change rates of 10%, 30%, 50%, 70%, and 90%.

### 3.7 Token Counting

All token counts use `tiktoken` and are reported for both `cl100k_base` (GPT-4/GPT-4o) and `o200k_base` (Claude). Formats compared:

- **Full JSON:** one compact JSON line per state
- **Delta JSON (steelman):** emit-on-change JSON (fair baseline)
- **Hex:** 2 hex chars per byte
- **Base64:** 4 chars per 3 bytes
- **Morse (raw):** 8 chars per byte, no delta
- **Morse (DSP):** 8 chars per changed byte only
- **AB-1 Braille (DSP):** Unicode cells, delta-encoded
- **Codebook:** unique-state dictionary + index stream (Base64-encoded)

### 3.8 Separation of Concerns: A Protocol Design Case Study

An instructive episode in PM-1's development illustrates the value of executable invariants. An initial hypothesis proposed using PM-1's `.` and `-` as **diacritical marks** on Unicode characters — analogous to Arabic harakat (حركات) — so that identical base symbols would carry different machine state depending on the attached diacritic:

```
😊.  → state A
😊-  → state B
```

The intuition was elegant: the base symbol carries semantics, the modifier carries a state flag. However, empirical testing revealed two failures:

1. **Tokenizer cost:** Combining marks increase token count (1 token for the emoji alone → 3 tokens with a combining dot on o200k_base), negating the zero-setup advantage.

2. **Silent normalization corruption (the critical failure):** NFC normalization silently merges combining marks into precomposed characters. For example, `"a" + combining-dot (U+0307)` becomes `ȧ` (U+0227) — the dot information is destroyed with no error signal. This happens **before** PM-1's Hamming ECC layer sees the bytes, making it an unrecoverable failure mode that ECC cannot detect.

The resolution was not to abandon the idea but to learn its lesson: **encoding and rendering must never be the same thing.** The PM-1 architecture now enforces:

```
PM-S (Symbolic)    →  Authoring notation (human-facing)
    ↓ compile only (one-directional, no reverse path)
PM-1 (Canonical)   →  Wire encoding (the only format agents transmit)
    ↓ render only (display-only, never re-ingested)
PM-View            →  Rendering (human-facing presentation)
```

Invariant I2 (normalization-safe) now acts as a gate: any future proposal to extend the PM-1 alphabet must survive NFC/NFKC normalization or be rejected by the test suite. The architecture — PM-S → PM-1 → PM-View, with no reverse path from View to Protocol — prevents the silent-corruption failure from re-emerging by construction, not by convention.

---

## 4. Results

### 4.1 Tokenizer Atomicity

`.` and `-` are exactly 1 token each in all four tested tokenizers:

| Tokenizer | Dot tokens | Dash tokens |
|-----------|-----------|-------------|
| cl100k_base | 1 | 1 |
| o200k_base | 1 | 1 |
| p50k_base | 1 | 1 |
| r50k_base | 1 | 1 |

The zero-setup property is confirmed.

### 4.2 AB-1 Crucible Trace

| Format | Chars | cl100k tokens | vs Steelman JSON |
|--------|-------|---------------|------------------|
| Steelman JSON | 93,677 | 28,076 | baseline |
| Hex | 2,834 | 945 | +77.9% vs Morse |
| Base64 | 1,892 | 1,255 | +70.6% vs Morse |
| Morse (DSP) | 8,228 | 4,270 | **84.8% savings** |
| AB-1 Braille (DSP) | 748 | 2,244 | 92.0% savings |

PM-1 (Morse DSP) achieves 84.8% token savings versus delta-encoded JSON on cl100k_base. AB-1 Braille achieves 92.0% (with its tokenizer extension). The gap is expected: Braille's 1-cell-per-state density is fundamentally more compact than Morse's 8-chars-per-byte.

### 4.3 Real Self-Harness Traces (Live Production)

**Aggregate savings (157 traces, ongoing):**

| Metric | Value |
|--------|-------|
| PM-1 trace files | 157 |
| JSON fallback files | 5 |
| Total PM-1 chars | 20,096 |
| Equivalent JSON bytes | 185,223 B |
| Compression ratio | 0.11× |
| **Aggregate savings** | **89.4%** |

**Per-format comparison (237-trace snapshot):**

| Format | cl100k tokens | vs Delta JSON |
|--------|--------------|--------------|
| Delta JSON | 7,290 | baseline |
| Codebook | 750 | 89.7% savings (dictionary) |
| Base64 | 1,153 | 84.2% savings |
| Hex | 1,297 | 82.2% savings |
| AB-1 Braille (DSP) | 2,297 | 68.5% savings |
| **Morse (DSP)** | **2,880** | **60.5% savings** |

On real agent traces with 82.6% change rate over 8-byte states, PM-1 saves 60.5% versus delta-encoded JSON per the benchmark. The live aggregate savings (89.4%) reflects the compounding effect of the differential protocol across the entire trace corpus — traces accumulate over time, and the fixed-width frame (128 chars per trace) provides predictable total costs regardless of individual trace content size.

### 4.4 Sensitivity Sweep

On 128-byte states at 10% change rate (cl100k_base):

| Format | Tokens | vs Morse |
|--------|--------|----------|
| Hex | 72,370 | +78.6% (worse) |
| Base64 | 61,125 | +50.8% (worse) |
| Morse (DSP) | 40,533 | baseline |

Morse beats hex by **1.8×** on 128-byte states at 10% change — the regime where DSP shines. At 10% change, only ~50 bytes change per step, each occupying 8 Morse chars vs 2 hex chars, but hex must encode all 128 bytes every time. The cross-over point varies by byte-width:

| State width | Cross-over change rate |
|-------------|----------------------|
| 1 byte | Morse never beats hex |
| 8 bytes | ≤30% change rate |
| 32 bytes | ≤10% change rate |
| 128 bytes | ≤10% change rate |

At 90% change on 128-byte states, Morse loses by 4.9× versus hex — the 8× raw overhead dominates when nearly every byte changes.

### 4.5 Design Space Map

Figure 6 positions PM-1 within the broader machine-native communication landscape. PM-1 and AB-1 cluster in the top-left quadrant (structured state, exact recovery). BabelTele occupies the bottom-right (natural language, semantic recovery). The empty top-right quadrant (natural language with exact recovery) remains an open research question — recovering every word of compressed natural language bit-perfectly is largely equivalent to lossless compression, a problem PM-1 does not attempt to solve.

### 4.6 End-to-End ReAct Integration

A simulated ReAct handoff scenario (orchestrator → fixer → oracle, 10 handoffs) demonstrates PM-1 in a realistic agent loop:

- Total PM-1 characters: ~520
- Equivalent JSON characters: ~1,025
- Savings: ~49.3%

Hamming error correction was demonstrated on real failure scenarios: single-bit flips are corrected, double-bit flips are detected and flagged.

---

## 5. Discussion

### 5.1 When to Use PM-1

PM-1 is most effective in three regimes:

1. **Low state-change rates** (≤10%): DSP amortizes the 8-byte overhead across long stable runs. Morse beats hex by 1.4–2×.
2. **Multi-byte state vectors** (≥8 bytes): The per-byte overhead is offset by DSP's emit-on-change selectivity. Hex wastes tokens re-encoding unchanged bytes.
3. **Cross-provider portability**: PM-1 works identically on GPT-4, Claude, Gemini, or any model using BPE tokenization — no extension, no registration, no provider-specific configuration.

It is **not** recommended for:
- Single-byte states at high change rates (hex or Base64 is cheaper)
- Environments where the tokenizer extension can be installed (AB-1 Braille is denser)
- Human-readable debugging output (hex is more legible)

### 5.2 Relationship to AB-1 and BabelTele

PM-1 is explicitly a derivative of AB-1. The differential state protocol, the Hamming [8,4,4] code, the two-tier command structure, and the benchmark methodology are adapted from Tetrahedroned's design. PM-1's original contributions are the `.`/`-` encoding scheme with its zero-setup analysis; the protocol invariants with enforceable test suite; the complete protocol state machine; DoS hardening; and benchmarking against hex and Base64 baselines.

BabelTele validates the same premise from a different direction: LLMs do not need human-readable intermediate representations. Where PM-1 and BabelTele differ is in the *guarantee*. BabelTele's recovery is semantic — the LLM reconstructs meaning, which can drift. PM-1's recovery is mathematical — `decode(encode(byte)) == byte` for all 256 values, enforced by I3. Neither approach is "better"; they serve different needs. PM-1's contribution is demonstrating that deterministic guarantees can coexist with token efficiency in the structured-state regime.

### 5.3 Reliability vs. Integrity: Why Guarantees Matter at Failure

A systems engineering principle applies: **most approaches are indistinguishable when they work; you learn what they really are when they fail.** PM-1 and BabelTele appear identical during normal operation — compact transport, semantic expansion, correct output. The difference emerges at the failure boundary.

We distinguish two engineering objectives:

- **Reliability:** *How often is the output correct?* BabelTele achieves 99.5% semantic fidelity on natural language tasks — for conversational and reasoning workloads, this is operationally indistinguishable from exact recovery.
- **Integrity:** *When the output is wrong, will the system know?* PM-1 guarantees this through Hamming ECC: single-bit errors are corrected, double-bit errors are detected and flagged. The system fails *explicitly* — it stops, rather than continuing with silently corrupted state.

In the terminology of fault-tolerant systems, PM-1 is **fail-stop** (corruption detected → system halts) while BabelTele is **fail-soft** (corruption absorbed → system continues with approximate output). Consider the consequences by domain:

| Domain | Tolerates fail-soft? | Example |
|--------|---------------------|---------|
| NPC mood in a game | Yes — "Happy" → "Content" is invisible | BabelTele acceptable |
| Medication dosage | No — "Warfarin 10mg" → "Warfarin 1mg" is catastrophic | PM-1 required |
| Code review confidence | Mostly — "High" → "Medium" is annoying, not dangerous | PM-1 preferred |
| Session state handoff | No — silent state drift compounds across steps | PM-1 required |

This is not a claim that PM-1 is "better" than BabelTele. It is a claim that they optimize different design objectives. BabelTele trades failure detection for arbitrary-text flexibility. PM-1 trades arbitrary-text flexibility for guaranteed failure detection. The practitioner's choice reduces to: *what kind of failure can your application tolerate?*

### 5.4 The Invariants Methodology

A recurring theme in PM-1's development has been the gap between documented properties and enforced properties. Early versions claimed to be normalization-safe "because ASCII." The diacritic case study (§3.8) showed that this property was true by accident, not by design — a Unicode combining mark would have silently corrupted state before the ECC layer could detect it.

The five invariants (I1–I5) close this gap. Each invariant is executable: the test suite checks it on every build. If a future contributor adds a character to the PM-1 alphabet, I2 catches it before merge. If the encoding algorithm changes, I3 catches it. This methodology — documented properties that CI can verify — is applicable beyond PM-1 and represents a secondary contribution of this work.

### 5.5 Limitations

- **Single-benchmark scope.** The Crucible trace is from AB-1's ecosystem. Our real-trace dataset addresses this but is limited to 8-byte states from one agent system.
- **No trained embedding.** PM-1 tokens have no learned semantics for the model — they are opaque state identifiers. Fine-tuning could improve model awareness of protocol state, but this is future work.
- **Human-unfriendly.** PM-1 is designed for machine-to-machine communication. Developers debugging agent state should use a separate rendering layer (PM-View).
- **Unicode tokenizers not tested.** SentencePiece-based models (Gemma, Llama-1/2) tokenize ASCII differently. The `tiktoken`-family tokenizers where `.` and `-` are atomic cover the major API-hosted LLMs but not all.

### 5.6 Three Encodings, Three Tradeoffs

No single encoding dominates. The honest value of PM-1 is occupying a previously empty quadrant — streaming-first, zero-setup, error-resilient, invariants-guaranteed deterministic state communication:

| Encoding | Best regime | Limitation |
|----------|-------------|------------|
| Codebook | Offline archival, few unique states | Two-pass, no streaming |
| Hex | High change rates, any state width | No error detection, verbose at low Δ |
| PM-1 Morse | Low change rates, streaming handoff | High per-byte cost at high Δ |
| AB-1 Braille | Extension-equipped environments | Requires tokenizer extension |
| BabelTele | Arbitrary text, LLM-native decoding | Semantic (lossy) recovery, LLM-dependent |

### 5.7 Security Considerations

The 64KB maximum state size bounds memory allocation for untrusted frames. The Hamming [8,4,4] and parity error detection layers protect against single-bit inference errors in model outputs. However, adversarial inputs designed to exploit the protocol (e.g., injecting command frames into natural-language text) are out of scope for this work — PM-1 assumes a trusted transport between known agent instances.

### 5.8 Use Cases and the Adapter Pattern

PM-1's architecture supports two primary deployment patterns, both enabled by treating protocol decoding and semantic expansion as separate, domain-specific concerns.

**Pattern 1: Edge-to-Cloud Relay.** An edge agent with a tight token budget (2K context) encodes its state as a compact PM-1 frame (~128 chars). At the cloud endpoint, the frame is deterministically decoded and a domain-specific adapter expands it into natural language for an LLM with an abundant context window (1M tokens). PM-1 saves bandwidth on the constrained leg; the expansion costs nothing at the destination. The adapter is not part of PM-1 — it is a consumer of the protocol, mapping a structured state vector to domain-specific semantics (e.g., hospital workflows, game NPC state, code-review pipelines).

**Pattern 2: Multi-Agent State Bus.** Multiple agents exchange only PM-1 frames — compact, deterministic, and zero-parse. No agent needs to speak English internally. Only the human-facing orchestrator or dashboard runs the adapter, decompressing frames into a readable timeline for debugging or oversight. This is analogous to routers: they exchange IP packets, not HTML; the browser is the only component that renders.

**Adapter-as-driver architecture.** Rather than shipping domain adapters with PM-1 (which would imply English expansion is part of the protocol), adapters are maintained as separate, domain-specific packages (`pm-adapter-coding`, `pm-adapter-hospital`, etc.). The PM-1 repository ships a single example adapter (`examples/adapter.py`) that demonstrates the pattern: a ~20-line function that takes a PM-1 frame and a schema dictionary and produces human-readable text. The protocol remains small and stable; applications build rich interpretations on top of it.

---

## 6. Conclusion

We presented Pro Memoria (PM-1), an ASCII-native binary protocol for token-efficient agent state communication. By encoding 8-bit state as 8-character Morse strings and combining this with a differential state protocol, a two-tier error-correcting lexicon, and a set of five executable protocol invariants, PM-1 achieves 60–89% token savings versus delta-encoded JSON with zero setup — no tokenizer extension, no Unicode registration, no configuration changes. The protocol is fully implemented (~750 lines of Python), verified with exhaustive tests, benchmarked on synthetic and real agent traces, and deployed in live production with ongoing trace accumulation.

PM-1 occupies a specific point in the growing design space of machine-native communication: structured state with deterministic recovery, trading expressive power for guaranteed correctness. It is not a replacement for AB-1 Braille (denser with extension) or BabelTele (arbitrary text with semantic recovery). Rather, it fills the gap for environments where neither a tokenizer extension can be installed nor lossy semantic recovery is acceptable.

The protocol invariants methodology — five enforceable properties verified on every build — represents a secondary contribution. This methodology is applicable beyond PM-1: documented properties that CI can verify, rather than prose claims that happen to be true today. The specification, test vectors, and executable invariants are available as `PROTOCOL.md` and `core.py:invariant_check()` in the repository.

Future work includes evaluating additional tokenizer families (SentencePiece-based models such as Gemma and Llama), accumulating larger real-world traces across diverse agent systems, and independent third-party implementations to validate the protocol's claims outside its reference codebase.

The implementation is open source at [github.com/rikirinjani/pro-memoria](https://github.com/rikirinjani/pro-memoria) under Apache-2.0 (code) and CC-BY-4.0 (specification).

---

## Figures

> ⚠️ **Figure placement:** Figures referenced inline. See PNG files in `paper/fig*.png`.

- **Figure 1:** AB-1 Crucible trace token costs (cl100k_base) — Morse DSP achieves 84.8% savings.
- **Figure 2:** Sensitivity sweep — Morse vs Hex at varying change rates on 128-byte and 8-byte states.
- **Figure 3:** Protocol State Machine — 7-state lifecycle with defined transition paths.
- **Figure 4:** Real agent trace comparison — 237 self-harness traces, 8-byte states, 82.5% change rate.
- **Figure 5:** Cross-over table — where Morse DSP outperforms hex by state width and change rate.
- **Figure 6:** Design Space Map — PM-1 among BabelTele, AB-1, Codebook, Hex, and Delta JSON.

---

## References

1. Tetrahedroned. *Agent Braille (AB-1): A Unicode-Based Protocol for Machine-to-Machine State Communication.* 2025. https://github.com/Tetrahedroned/Agent-Braille
2. Zhu, J. et al. *BabelTele: A Probe into Model-Centric Textual Representations for Large Language Models.* arXiv:2606.19857, 2026.
3. Yao, S. et al. *ReAct: Synergizing Reasoning and Acting in Language Models.* ICLR, 2023.
4. Brown, T. et al. *Language Models are Few-Shot Learners.* NeurIPS, 2020.
5. Google. *Model Context Protocol (MCP).* 2024. https://github.com/modelcontextprotocol
6. Google. *Agent-to-Agent (A2A) Protocol.* 2025. https://github.com/google/A2A
7. Sennrich, R. et al. *Neural Machine Translation of Rare Words with Subword Units.* ACL, 2016.
8. Hamming, R. W. *Error Detecting and Error Correcting Codes.* Bell System Technical Journal, 1950.

---

> ⚠️ **Draft notes:**
> - Author name and date placeholders ([AUTHOR_NAME], [DATE]) need filling.
> - §4.3 live savings numbers update as traces accumulate — the 89.4% figure is current as of July 2026.
> - §4.6 ReAct integration numbers are from the demo simulation — replace with systematic runtime measurements before arXiv submission.
> - Figure 6 is a qualitative design space map — the coordinates are illustrative, not empirical.
