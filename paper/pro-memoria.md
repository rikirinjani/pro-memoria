# Pro Memoria: An ASCII-Native Binary Protocol for Token-Efficient Agent State Communication

> **Authors:** Riki, inspired by Tetrahedroned/Agent-Braille (Apache-2.0, CC-BY-4.0)
>
> **Repository:** https://github.com/rikirinjani/pro-memoria

---

## Abstract

Large language model (LLM) agents generate significant token overhead tracking their internal state across multi-step tasks. Existing compact state representations either require tokenizer extensions (e.g., Agent Braille) or remain tied to JSON with modest compression. We present **Pro Memoria (PM-1)** , an ASCII-native binary protocol that encodes 8-bit state as 8-character Morse strings (`.` = 0, `-` = 1), combined with a Differential State Protocol (DSP) that emits only changed bytes and a two-tier error-correcting command lexicon (Hamming [8,4,4] with single-error correction and parity with single-error detection). Because `.` and `-` are unconditionally single tokens in every major tokenizer (cl100k_base, o200k_base, p50k_base, r50k_base — verified), PM-1 requires **zero setup**: no vocabulary extension, no Unicode registration, no configuration changes. On the AB-1 Crucible trace (1,417 single-byte states), PM-1 achieves 84.8% token savings versus delta-encoded JSON (cl100k_base). On 243 real agent self-harness traces (8-byte state vectors, 82.6% change rate), it achieves 60.5% savings. A sensitivity sweep across 1–128 byte states and 10–90% change rates shows PM-1 beats hex by 1.4–2× at ≤10% change rates on multi-byte states. PM-1 is implemented in ~750 lines of pure Python with zero dependencies and a documented 7-state protocol machine.

---

## 1. Introduction

LLM agents increasingly use structured internal state to track progress across multi-step tasks: tool calls completed, files touched, confidence levels, error counts, phase transitions, and outcome flags. As agent frameworks (ReAct, function-calling loops, orchestrate–act–observe pipelines) grow in sophistication, the volume of state-tracking tokens grows correspondingly.

The standard approach — serializing state as compact JSON — produces verbose output even with minimized field names and whitespace. A single agent state transition (agent ID, phase, confidence, tool calls, files, outcome) consumes ~60–100 characters or ~20–40 tokens depending on the tokenizer. Over hundreds of steps in a typical agent session, this overhead accumulates to thousands of tokens — pure scaffolding that carries no semantic information for the task at hand.

Recent work has proposed more efficient encodings. **Agent Braille (AB-1)** [Tetrahedroned, 2025] encodes 8-bit agency state as single Unicode Braille cells (U+2800–U+28FF), achieving ~92% token savings versus delta-encoded JSON via a Differential State Protocol (DSP) and a hardened command lexicon. AB-1's core insight — that agent state is low-entropy and benefits dramatically from delta-encoding — is well-established. However, AB-1 requires a **tokenizer extension** to map Braille cells to single tokens. Without it, each Braille cell fragments into ~3 byte-tokens on stock tokenizers, eliminating the savings.

We present **Pro Memoria (PM-1)** , which adopts AB-1's DSP and Hamming [8,4,4] math but replaces the Unicode Braille encoding layer with ASCII `.` and `-` characters. Our key observation is that `.` and `-` are atomic (single-token) in **every** production tokenizer without any extension. This yields a zero-setup protocol: the same 84–92% token savings regime as AB-1, but portable across any LLM provider or tokenizer without configuration.

The tradeoff is encoding density. AB-1 fits one 8-bit state in a single Unicode cell (~1–3 tokens). PM-1 requires 8 ASCII characters per byte, which is inherently 8 tokens per byte. At low state-change rates (≤10%), DSP ensures PM-1's per-byte cost is amortized across long stable runs. At high change rates, the 8× raw overhead dominates and simpler encodings like hex (2 chars/byte) outperform.

**Contributions:**

1. **PM-1 encoding** — a deterministic, roundtrip-safe mapping from 8-bit bytes to 8-character Morse strings (`.` = 0, `-` = 1), verified for all 256 byte values.
2. **Zero-setup property** — proof that `.` and `-` are single tokens in cl100k_base, o200k_base, p50k_base, and r50k_base, making PM-1 immediately usable in any LLM environment.
3. **Differential State Protocol** — emit-on-change frame format with grow/shrink support and configurable maximum state size (64KB DoS guard).
4. **Two-tier error-correcting lexicon** — 16 Hamming [8,4,4] commands (single-bit correction, double-bit detection) and 128 parity-protected commands (single-bit detection), occupying the same 8-bit encoding space with explicit tier routing.
5. **Comprehensive benchmarks** — evaluation on the AB-1 Crucible trace, 237 real agent self-harness traces, and a sensitivity sweep over byte-width and change rate.

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

### 2.2 Existing Compact Encodings

**Hex encoding** (2 chars/byte) and **Base64** (4 chars per 3 bytes ≈ 1.33× overhead) are both ASCII-native and zero-setup. Hex is the simplest baseline: 16 tokens per byte (each nybble is one hex char). Base64 achieves 1.33 tokens per byte but requires padding and is less human-readable. Both are included as baselines in our benchmarks.

**UTF-8 direct encoding** of ASCII-range bytes maps 1:1 to tokens in BPE tokenizers, but this is merely the raw representation — no compression.

**Codebook compression** exploits low unique-state counts in agent trace data. When an agent session produces only 106 unique states out of 237 transitions, a codebook mapping each unique state to a 1-byte index and transmitting the codebook + index stream achieves strong compression. We include codebook as an additional baseline for the real-trace benchmark, noting it requires both encoder and decoder to share the codebook table.

### 2.3 Structured State Compression

Prior work on state delta trajectories (latent-space deltas), A2A (agent-to-agent transport), and MCP (Model Context Protocol) addresses different parts of the agent communication stack. PM-1 is orthogonal to these: it compresses the state *representation* that travels over any transport.

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

### 3.2 Differential State Protocol (DSP)

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

### 3.3 Lexicon: Two-Tier Error Correction

PM-1 defines two command tiers that share the same 8-bit encoding space:

**Tier 1 — Hamming [8,4,4] (16 commands, distance 4):** Uses an extended Hamming code. Four data bits are encoded into eight bits with three syndrome bits and one overall parity bit. Single-bit errors are corrected; double-bit errors are detected. The 16 commands (NOP, ACK, NAK, RESET, SYNC, REQ, DATA, EOF, ERR, RETRY, STATUS, CONFIG, HELLO, BYE, ECHO, HALT) implement the protocol control layer.

**Tier 2 — Parity-protected (128 commands, distance 2):** Seven data bits plus even parity in the MSB. Any single-bit error is detected. These commands extend the protocol with application-level operations (STATE_REQ, STATE_REP, DIFF, FULL_SYNC, COMPRESS, etc.).

**Tier collision:** The value `0x87` is a valid codeword in both tiers (Hamming command 7 = EOF; parity command 7 = FULL_SYNC). The protocol requires explicit tier specification — auto-detection is intentionally not supported.

### 3.4 Protocol State Machine

PM-1 defines a 7-state connection lifecycle:

| State | Purpose | Key Commands |
|-------|---------|-------------|
| CLOSED | No connection | HELLO, VERSION |
| HANDSHAKE | Version negotiation | VERSION, VERSION_ACK, ACK, NAK |
| SYNCING | Full state sync | SYNC, STATE_REP, ACK |
| DATA | Normal operation | DIFF, FULL_SYNC, ECHO, STATUS, ERR |
| ERROR | Recoverable error | RETRY, RESET, STATUS |
| RECOVERY | Re-syncing | RESET, REQ, STATE_REP, ACK |
| DISCONNECT | Clean shutdown | BYE, HALT |

Version capability negotiation uses reserved parity commands `VERSION` (0x0E) and `VERSION_ACK` (0x0F) as the mandatory first exchange in any handshake.

### 3.5 Benchmark Datasets

We evaluate on two datasets:

**AB-1 Crucible trace.** 1,417 single-byte state snapshots from AB-1's benchmark suite, representing an 8-dimensional agency model (I/O, logic, source, privacy, temporal, audit, priority). Only 6 unique masks; 748 state changes (52.8% emit ratio).

**Real self-harness traces.** 243 traces from actual agent sessions in the self-harness system, encoded as 8-byte state vectors (agent type, outcome, duration bucket, tool-calls bucket, files bucket, failure category, failure severity, validation flag). 106 unique states; 82.6% state-change rate. 12% of traces are non-standard (timeline entries, meta-platform events) missing duration and key_files fields — these are marked with a completeness flag (byte 7, bit 1) to distinguish "field not present" from "zero value."

We also generate synthetic states for sensitivity analysis: 500-step sequences at byte widths of 1, 8, 32, and 128, with change rates of 10%, 30%, 50%, 70%, and 90%.

### 3.6 Token Counting

All token counts use `tiktoken` and are reported for both `cl100k_base` (GPT-4/GPT-4o) and `o200k_base` (Claude). Formats compared:

- **Full JSON:** one compact JSON line per state
- **Delta JSON (steelman):** emit-on-change JSON (fair baseline)
- **Hex:** 2 hex chars per byte
- **Base64:** 4 chars per 3 bytes
- **Morse (raw):** 8 chars per byte, no delta
- **Morse (DSP):** 8 chars per changed byte only
- **AB-1 Braille (DSP):** Unicode cells, delta-encoded
- **Codebook:** unique-state dictionary + index stream (Base64-encoded)

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

Against the trivial ASCII baselines: hex is 77.9% cheaper than Morse on single-byte states because hex (2 chars/byte) always wins on single-byte, high-frequency-change workloads. The Morse advantage emerges on multi-byte states with low change rates.

### 4.3 Real Self-Harness Traces (237 traces, 8-byte states)

| Format | cl100k tokens | vs Delta JSON |
|--------|--------------|--------------|
| Delta JSON | 7,290 | baseline |
| Codebook | 750 | 89.7% savings (dictionary) |
| Base64 | 1,153 | 84.2% savings |
| Hex | 1,297 | 82.2% savings |
| AB-1 Braille (DSP) | 2,297 | 68.5% savings |
| **Morse (DSP)** | **2,880** | **60.5% savings** |

On real agent traces with 82.6% change rate over 8-byte states, PM-1 saves 60.5% versus delta-encoded JSON. The high change rate (82.6%) reduces DSP's advantage — most steps emit a diff — so hex (1,297 tokens) and Base64 (1,153 tokens) outperform Morse here. Codebook compression wins on this data shape by exploiting the limited unique-state palette (106/237). The AB-1 Braille result (2,297 tokens) reflects correct multi-byte state encoding across all 8 bytes per trace.

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

### 4.5 End-to-End ReAct Integration

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

### 5.2 Relationship to AB-1

PM-1 is explicitly a derivative of AB-1. The differential state protocol, the Hamming [8,4,4] code, the two-tier command structure, and the benchmark methodology are adapted from Tetrahedroned's design. PM-1's original contributions are:

- The `.`/`-` encoding scheme and its zero-setup analysis
- The complete protocol state machine (7 states, handshake/recovery sequences)
- The DSP relay semantics (apply() returns the forwarded frame)
- DoS hardening (MAX_STATE_BYTES)
- Benchmarking against hex and Base64 baselines on multi-byte states

We believe PM-1 occupies a useful niche in the design space: it trades AB-1's superior density for universal portability. An agent framework cannot assume a tokenizer extension is installed; it can always assume ASCII works.

### 5.3 Hybrid PM-1 / AB-1 Encoding

PM-1 and AB-1 are not competing protocols — they occupy complementary positions in the same stack. PM-1 Morse is the universal bootstrap: it requires zero setup, works in any LLM environment, and guarantees that the first connection always succeeds. AB-1 Braille is the density upgrade: once the handshake confirms both sides support the tokenizer extension, ongoing DATA-phase communication can use Braille cells at ~20% lower token cost.

The protocol state machine already supports this: the HANDSHAKE phase negotiates protocol version before any state data is exchanged. We extend this with `ENCODING` and `ENCODING_ACK` commands, so the initiator advertises `{morse, braille}` and the responder selects the best shared encoding. On error recovery or disconnect, the encoder resets to Morse (universal). This layering — PM-1 for bootstrap, AB-1 for ongoing density — gives each protocol the role it is best suited for, with zero additional configuration burden.

### 5.4 Limitations

- **Single-benchmark scope.** The Crucible trace is from AB-1's ecosystem. Our real-trace dataset addresses this but is limited to 8-byte states from one agent system.
- **No trained embedding.** PM-1 tokens have no learned semantics for the model — they are opaque state identifiers. Fine-tuning could improve model awareness of protocol state, but this is future work.
- **Human-unfriendly.** PM-1 is designed for machine-to-machine communication. Developers debugging agent state should use a separate rendering layer.
- **Unicode tokenizers not tested.** SentencePiece-based models (Gemma, Llama-1/2) tokenize ASCII differently. The `tiktoken`-family tokenizers where `.` and `-` are atomic cover the major API-hosted LLMs but not all.

### 5.4 Security Considerations

The 64KB maximum state size bounds memory allocation for untrusted frames. The Hamming [8,4,4] and parity error detection layers protect against single-bit inference errors in model outputs. However, adversarial inputs designed to exploit the protocol (e.g., injecting command frames into natural-language text) are out of scope for this work — PM-1 assumes a trusted transport between known agent instances.

---

## 6. Conclusion

We presented Pro Memoria (PM-1), an ASCII-native binary protocol for token-efficient agent state communication. By encoding 8-bit state as 8-character Morse strings and combining this with a differential state protocol and a two-tier error-correcting lexicon, PM-1 achieves 60.5–84.8% token savings versus delta-encoded JSON with zero setup — no tokenizer extension, no Unicode registration, no configuration changes. The protocol is fully implemented (~750 lines of Python), verified with exhaustive tests (256-byte roundtrip, 128/128 Hamming corrections, 56 DSP edge cases), and benchmarked on both synthetic and real agent traces.

PM-1 is not a replacement for AB-1 Braille, which achieves superior density through its tokenizer extension. Rather, PM-1 fills the gap for environments where an extension cannot be installed but token-efficient state communication is still required.

The implementation is open source at [github.com/rikirinjani/pro-memoria](https://github.com/rikirinjani/pro-memoria) under Apache-2.0 (code) and CC-BY-4.0 (specification).

---

## References

1. Tetrahedroned. *Agent Braille (AB-1): A Unicode-Based Protocol for Machine-to-Machine State Communication.* 2025. https://github.com/Tetrahedroned/Agent-Braille
2. Yao, S. et al. *ReAct: Synergizing Reasoning and Acting in Language Models.* ICLR, 2023.
3. Brown, T. et al. *Language Models are Few-Shot Learners.* NeurIPS, 2020.
4. Google. *Model Context Protocol (MCP)*. 2024. https://github.com/modelcontextprotocol
5. Google. *Agent-to-Agent (A2A) Protocol.* 2025. https://github.com/google/A2A
6. Sennrich, R. et al. *Neural Machine Translation of Rare Words with Subword Units.* ACL, 2016.
7. Hamming, R. W. *Error Detecting and Error Correcting Codes.* Bell System Technical Journal, 1950.

---

> ⚠️ **Note:** Sections 4.2–4.4 contain empirical measurements from the codebase benchmarks. Section 4.5 contains projected results from the ReAct integration demo — replace with systematic runtime measurements before submission.
