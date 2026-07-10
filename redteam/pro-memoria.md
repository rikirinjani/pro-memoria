# Pro Memoria — Red-team Report

> ⚠️ **模拟结果,非真实评审。** 真实评审受 venue、审稿人抽样、当年竞争激烈程度影响,这里只反映"以当前草稿的状态,大概率会撞上哪些枪"。

**Review target:** Pro Memoria — ASCII-native binary protocol for AI agent state communication
**Venue:** NeurIPS (default ML/AI engineering conference scale)
**Date:** 2026-07-10

---

## Reviewer: R1 — The Champion

**Summary.**
Agent Morse defines a lossless 8-bit → 8-char encoding using '.' and '-' (Morse-like), a differential state protocol that emits only changed bytes, and a two-tier error-hardening layer (Hamming [8,4,4] for 16 commands, simple parity for 128). It's benchmarked against both JSON baselines and AB-1 Braille on the AB-1 Crucible trace (1,417 state snapshots). The core claim is ~85% token savings vs delta-JSON with zero-setup — no tokenizer extension, no Unicode, no vocab changes.

**Strengths.**

- **Clever zero-setup property.** The idea that ASCII '.' and '-' are inherently 1 token/char in every tokenizer is well-founded. No extension, no registry, no special-casing. This is a genuine engineering advantage over AB-1. [core.py:7-11]

- **Complete, tested implementation.** 4 phases built and verified: roundtrip for all 256 bytes, 128/128 single-error Hamming corrections, 448/448 double-error detections, 56/56 DSP edge cases, and a real-trace benchmark. This is more than most protocol proposals provide. [core.py:57-64, lexicon.py:230-260, bench/test_dsp.py]

- **Honest benchmark methodology.** The benchmark correctly uses steelman delta-JSON as the fair baseline (not naive per-step JSON), follows AB-1's own methodology, and reports the Morse-vs-AB-1 gap transparently (−90%). No cherry-picking of metrics. [bench/token_efficiency.py:6-12]

- **DSP layer is well-designed.** The emit-on-change DiffState class handles grow, shrink, truncation cleanly. The frame format (index:8morse|) is compact and parseable. [dsp.py:12-18]

**Weaknesses.**

1. 🟡 **Single trace dataset limits generalizability** — The benchmark uses only the AB-1 Crucible trace (1,417 states, 6 unique masks, 7 dimensions). This is one workload. Real agent state may have more dimensions, larger state vectors, or different change patterns. [bench/results/token_efficiency.json:2-6]
   → This is acknowledged in positioning but warrants a 🟡 — the 85% number is not yet a universal bound.

2. 🟢 **Hamming command table is underspecified** — The 16 Hamming commands (NOP, ACK, NAK, etc.) are plausible but have no formal protocol semantics defined. How does HELLO vs SYNC vs REQ interact? What's the state machine? [lexicon.py:186-203]
   → Not a fatal gap for a protocol spec, but the lexicon feels like a placeholder.

3. 🟢 **No real agent integration** — The protocol hasn't been tested inside an actual agent loop (e.g., as a drop-in for JSON state tracking in a real LLM tool-use session). All tests are unit-level. This limits confidence in the "zero-setup" claim for real-world use.

**Questions to authors.**

- What is the target agent framework? Can you show a concrete integration (e.g., replacing the scratchpad in a simple ReAct loop)?
- For the 14 parity commands defined — are these intended as a complete protocol, or illustrative?

**Ratings** (NeurIPS scale; simulated, not real review):
- Soundness: 3/4 — Good implementation, honest benchmark, but limited evidence scope.
- Presentation: 3/4 — Clearly written code and docs, but protocol semantics underspecified.
- Contribution: 3/4 — Novel combination (Morse + DSP + Hamming), demonstrable savings.
- **Overall:** 7/10 — Solid engineering contribution. Compelling for the zero-setup niche.
- Confidence: 4/5

---

## Reviewer: R2 — The Methodological Skeptic

**Summary.**
A protocol that encodes 8-bit state as 8-char "." and "-" strings, with differential state emission and optional error correction. Claims ~85% token reduction vs delta-JSON on the AB-1 Crucible trace. Positioned as a zero-setup alternative to AB-1 Braille.

**Strengths.**

- The roundtrip and error-correction tests are thorough. 128/128 single-bit corrections verified across all 16 codewords at all 8 bit positions. [lexicon.py:240-253]
- The DiffState class correctly handles the full lifecycle: init, grow, shrink, no-change. 56/56 edge case tests. [bench/test_dsp.py]

**Weaknesses.**

1. 🔴 **Benchmark compares against only one trace, and that trace is from AB-1's own suite.** The Crucible trace was designed for AB-1's 8-dimensional agency model. Using it to evaluate Morse is convenient but circular — both encodings trivialize the same 7-field state into a single byte. Real agent state (function call args, tool outputs, intermediate variables) is much larger than 7 dimensions. The 85% number may not generalize to byte strings >1 byte. [bench/token_efficiency.py:20-28, token_efficiency.json:2-6]

2. 🔴 **The 85% vs steelman claim conflates two sources of gain: (a) delta-encoding, and (b) Morse's compact symbol.** The benchmark does decompose this (47.1% from delta-encoding alone), but the headline "85%" includes both. The Morse-specific contribution is the *remaining* savings on top of delta-encoding: (1 − 4270/28076) for steelman vs (1 − 28076/53043) for delta — i.e., ~85% − 47% = ~38 percentage points are Morse-specific. This is still good, but the 85% headline could mislead. [token_efficiency.json:14-17]

3. 🟡 **No statistical robustness reported.** Single benchmark run, no variance, no sensitivity to trace characteristics (state change frequency, number of dimensions, byte-level entropy). The Crucible trace has only 6 unique masks out of 1,417 states — that's a very low-entropy environment that favors any delta-encoding scheme. What happens at 90% change rate vs 10%? [token_efficiency.json:3-5]

4. 🟡 **8 tokens per byte is a hard floor.** AB-1 can theoretically reach 1 token/state with its extension; Morse is always 8 tokens/byte. For multi-byte state (e.g., 10 bytes = 80 tokens), the Morse overhead compounds linearly. The benchmark only tests single-byte states. [core.py:15-29]

5. 🟢 **Token counting uses tiktoken's `encode()` without checking for special token handling.** The '.' and '-' are ASCII and should be single tokens, but this should be explicitly verified per tokenizer. Some tokenizers merge adjacent punctuation. [bench/token_efficiency.py:88-91]

**Questions to authors.**

- Have you tested with multi-byte state vectors (e.g., 8–64 bytes)? The 1-byte Crucible case is the absolute best case for Morse.
- What happens at high state-change rates (e.g., 80%+)? At that point, DSP provides little benefit and the 8-char/byte cost dominates.
- The parity-protected commands — are these meant to travel alongside the DSP frames, or as a separate channel? The interplay between the DSP layer and the lexicon layer is not defined.

**Ratings** (NeurIPS scale; simulated):
- Soundness: 2/4 — Honest within the tested scope, but scope is narrow and evidence insufficient to support the claimed generality.
- Presentation: 3/4 — Clear code, underspecified protocol semantics.
- Contribution: 2/4 — Incremental over AB-1's DSP. The zero-setup advantage is real but narrow.
- **Overall:** 5/10 — Interesting idea with solid implementation, but the evidence base is too narrow for the strength of the claims.
- Confidence: 4/5

---

## Reviewer: R3·AC — The Novelty Hawk

**Summary.**
Agent Morse replaces Unicode Braille cells (AB-1) with ASCII '.' and '-' for binary state encoding, layered on the same differential state protocol idea from AB-1. Claims ~85% token savings vs JSON for state tracking, zero-setup.

**Strengths.**

- The 1-token-per-ASCII-character insight is clean and well-demonstrated. It genuinely removes the tokenizer-extension barrier that AB-1 faces.
- The benchmark includes a decomposition of gains (delta-encoding vs symbol compaction), which is rare and appreciated.

**Weaknesses.**

1. 🔴 **"Not X + Y" problem: this is AB-1's DSP with a different encoding layer.** The differential state protocol, emit-on-change discipline, Hamming [8,4,4] error correction (identical math per the spec), and the benchmark dataset are all taken from AB-1. The true novelty is (a) encoding scheme ('.'/'−' instead of Braille) and (b) the zero-setup corollary. That is a real but narrow delta. [memory.txt:88-92, lexicon.py:1-6]

2. 🔴 **Novelty is a one-time insight.** The core encoding idea (bit→'.'/'−') is ~50 lines of code. Once published, it's immediately reproducible. The contribution is the *analysis* that this yields 85% savings with zero-setup, not the engineering. The paper would be a 4-page note, not a full conference paper. [core.py:15-54]

3. 🟡 **Related work positioning is incomplete.** The comparison is against AB-1 and JSON baselines, but what about:
   - Base64 encoding? (Also ASCII, no extension, 4 chars per 3 bytes = 1.33x overhead)
   - Hex encoding? (2 chars per byte)
   - Direct UTF-8 encoding? (1 token per byte for ASCII-range bytes)
   The claim "85% vs JSON" needs to be contextualized against *these* trivial alternatives, not just AB-1. [bench/token_efficiency.py]

4. 🟡 **The Hamming lexicon (16 commands) borrows directly from AB-1's math** with the same [8,4,4] code. The parity tier (128 commands) is a simple parity bit — not novel. The claimed two-tier system is best described as "AB-1's Hamming layer + 1-bit parity extension," not a new contribution. [lexicon.py:1-11]

5. 🟢 **The "paper" is not written yet.** Only a benchmark and code exist. The protocol semantics, wire format spec, integration guide, and edge-case analysis are all absent.

**Questions to authors.**

- If I strip away AB-1's DSP and Hamming math, what is left that is specifically *Morse*? The encoding scheme. Is that enough for a standalone paper?
- Have you considered positioning this as a **short note / systems paper** rather than a full conference submission? The contribution-to-length ratio favors a workshop or 4-page format.
- Did you test hex encoding as a baseline? Hex is 2 chars/byte, also ASCII, also zero-setup. 16 tokens per byte vs morse's 8 tokens per byte — morse wins 2×, but hex is more human-readable. Why not just use hex?

**Ratings** (NeurIPS scale; simulated):
- Soundness: 3/4 — Within scope, evidence is solid.
- Presentation: 2/4 — No paper yet. Code is clean but protocol semantics undefined.
- Contribution: 2/4 — Real but narrow delta over AB-1. Novelty is the encoding scheme + analysis.
- **Overall:** 5/10 — Interesting systems note, not a full research paper. "X + Y but with '.' and '-'" assessment.
- Confidence: 4/5

---

## Area Chair Meta-review

**Consensus weaknesses (multiple reviewers point to = most dangerous):**

- 🔴 **Evidence scope is too narrow for generality claims.** R2 and R3 both flag that the single-trace, 1-byte-state benchmark doesn't support the implied generality of "85% savings." [R2⚡1, R3⚡3]
- 🔴 **Novelty delta over AB-1 is thin.** R3's "this is AB-1's DSP with a different encoding" is echoed by R2's observation that 47% of the claimed savings come from delta-encoding, not Morse. [R2⚡2, R3⚡1, R3⚡4]
- 🟡 **Protocol semantics undefined.** Both R1 and R2 note that the Hamming/parity command table has no defined interaction model or state machine. [R1⚡2, R2⚡Q3]

**Split opinions:**
- **R1 vs R2/R3 on contribution magnitude.** R1 sees a solid 7/10 engineering contribution. R2 and R3 rate it 5/10, viewing the novelty as narrow. The split reflects different weight on "zero-setup" — R1 values it highly, R2/R3 see it as a minor advantage over hex/base64/AB-1.
- **R1 vs R2 on soundness.** R1 accepts the benchmark as sufficient for a protocol proposal (3/4). R2 demands multi-byte, multi-trace, and sensitivity analysis (2/4).

**Decisive factors (2–3 that will determine outcome):**

1. **Multi-byte state testing.** If Morse's 85% holds for 8-byte or 32-byte state vectors, the contribution is much stronger. If it degrades to parity with hex, the paper is a note.
2. **Positioning clarity.** If positioned as a "portable binary protocol for agent state" with comparisons to hex/base64/AB-1, it's defensible. If positioned as "85% vs JSON" without caveats, reviewers will penalize.
3. **Paper draft quality.** With only code, there's nothing to review. The framing and contextualization matter enormously for a narrow-delta contribution.

**Predicted outcome:** `Borderline — more likely Reject at NeurIPS, could be Accept at systems/workshop venue`

> ⚠️ 模拟结果,非真实评审。真实评审受 venue、审稿人抽样、当年竞争激烈程度影响。

**One-line verdict.** Interesting systems note with a real but narrow contribution; the zero-setup encoding insight is solid, but the current evidence base and novelty depth aren't enough for a top-tier venue.

---

## Pre-submission Fix List (按优先级)

### 🔥 高影响 · 低成本（先改这些,最划算）

- [ ] **Add hex and Base64 baselines to benchmark** [R3⚡3]
      怎么改:Add hex() and base64.b64encode() as additional encoding columns in token_efficiency.py. These are the obvious trivial alternatives and not having them invites reviewer pushback.
      赶得上吗:✅ deadline 内可做 (~30 minutes).

- [ ] **Multi-byte state benchmark (8, 32, 128 bytes)** [R2⚡1, R2⚡4, R3⚡3]
      怎么改:Generate synthetic states of varying byte-lengths, run the same three-way comparison. 8 bytes = 64 Morse chars, which is the sweet spot to test the linear-scaling concern.
      赶得上吗:✅ deadline 内可做 (extend token_efficiency.py with --state-sizes flag).

- [ ] **Add change-rate sensitivity sweep** [R2⚡3]
      怎么改:Test Morse at 10%, 30%, 50%, 70%, 90% state-change rates (synthetic). This isolates when DSP helps vs hurts.
      赶得上吗:✅ deadline 内可做 (extend the synthetic_session generator from AB-1's bench).

- [ ] **Verify per-tokenizer atomicity of '.' and '−'** [R2⚡5]
      怎么改:Add an explicit test that `len(enc.encode('.')) == 1` and `len(enc.encode('-')) == 1` for cl100k_base, o200k_base, p50k_base, r50k_base.
      赶得上吗:✅ deadline 内可做.

### 🧱 高影响 · 高成本（尽早动手）

- [ ] **Test on a real agent trace (not AB-1 Crucible)** [R2⚡1, R1⚡1]
      怎么改:Run an actual agent (e.g., a ReAct loop on HotpotQA or ToolBench) and capture real state transitions. This is the only way to rebut "the trace is from AB-1's ecosystem."
      赶得上吗:⏳ 需要新实验(1–2 天搭建 agent loop + capture).

- [ ] **Define the full protocol semantics** [R1⚡2, R2⚡Q3]
      怎么改:Write a protocol spec covering: (a) how Hamming commands and parity commands interact with DSP frames, (b) handshake/handoff state machine, (c) error recovery procedure on uncorrectable frames.
      赶得上吗:⏳ 需要设计工作(1–2 天草案).

### 🧹 低成本打磨（顺手清掉）

- [ ] **Reposition the headline to be precise** [R2⚡2]
      Change "85% vs JSON" → "85% vs delta-JSON on compressed single-byte state; ~38pp is Morse-specific, ~47pp from delta-encoding." Save the stronger claim for the conclusion after discussion.

- [ ] **Document the 0x87 collision (EOF = Hamming cmd 7 = FULL_SYNC = parity cmd 7)** [memory.txt]
      The collision is known but undocumented in code. Add a comment and mechanism for explicit tier routing.

- [ ] **Add real-world integration example** [R1⚡3]
      Even a 20-line example showing Morse replacing JSON in a simulated ReAct scratchpad would dramatically strengthen the paper.

---

## Quality Gate Checklist

### 通用(两种模式):
1. ✅ 每条 weakness 都有出处或 `⚠ MISSING / 未定位` 标注?
2. ✅ 每条 weakness 都分了级(🔴/🟡/🟢)?
3. ✅ 🔥 **每条 weakness 都过了 H1–H17 公正性防火墙?**
   - H1 "结果不令人惊讶" → 未使用
   - H3 "结果不新颖" → R3's "not X + Y" has specific citations to AB-1 (memory.txt:88-92, lexicon.py:1-6) → passes firewall
   - H5 "没超 SOTA" → 未使用; comparison is to AB-1, not SOTA
   - H7 "方法太简单" → R3⚡2 raises this but grounds it in specificity (50 lines of code, 4-page note) → passes because it's not "too simple" as a dismissal, it's about scope
   - H13 "作者本可以再做实验 X" → R2's "multi-byte testing" and "sensitivity sweep" are grounded in the paper's own claims (85% generality) → passes because they directly test the claimed scope, not "more experiments for completeness"
   - H16 "有局限 = 有缺陷" → 未使用
4. ✅ 有没有为凑数硬挑的假 weakness? → No. All weaknesses are grounded in specific code/files.
5. ✅ 每份 review 的 Summary 都能证明真读懂了?
6. ✅ 🔴 与 🟡 分得清?

### Mode A 专项:
7. ✅ 预测结局显式标了"模拟,非真实评审"?
8. ✅ fix-list 按"影响×成本"排序,每条都有"赶得上吗"标注?
