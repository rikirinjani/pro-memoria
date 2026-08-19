# PM-1 / Pro Memoria — V0.5 Publication Design

Role: OG Pro Memoria / PM-1 architect + scientific paper architect.
Status: design document — no experiments run, no API calls, no artifacts modified.
Date: 2026-08-18

---

## 1. Publication Structure Recommendation

### Option comparison

**Option A — One paper** (PM-1 architecture + PM-Adapter + V0.1–V0.5).

- Coherence: weak. PM-Adapter is a schema-adapter component that V0.5 does not
  use. Including it forces the reader to track two different systems with two
  different evaluation targets inside one narrative.
- Contribution density: diluted. The scientific core (skip-based handoff
  economics) competes with implementation documentation for attention.
- Reviewer expectations: an empirical systems paper with a clear hypothesis is
  stronger than a combined architecture+implementation+experiments document.
  A single paper risks "too broad" review, and any weakness in the adapter
  section contaminates the experimental section.
- Verdict: weakest option.

**Option B — Two full papers** (PM-1 paper; PM-Adapter paper).

- PM-Adapter paper viability: currently insufficient. Its contribution is a
  deterministic schema-adapter separating PM-1 transport from domain schemas,
  backed by verification records. Without a second experimental evaluation of
  the adapter itself (e.g., schema-fidelity benchmarks, adapter-only error
  taxonomy), a full paper would be padded.
- Coherence of the PM-1 paper: unchanged by B, but B pays the cost of claiming
  a second paper before the evidence supports one.
- Risk: salami-slicing criticism ("same benchmark table in both papers") that
  reviewers already flag on this program's earlier material.
- Verdict: premature; revisit only if a dedicated adapter evaluation is run.

**Option C — One primary scientific paper + software/technical note for
PM-Adapter.** *(RECOMMENDED)*

- The scientific contribution is a single hypothesis: skip-based handoff
  transmits bounded continuation state and changes long-horizon cumulative
  token economics. One paper, one narrative, one claim hierarchy.
- PM-Adapter is honestly presented as the reference implementation and
  documented as a software artifact (repository + schema + verification
  records + technical note). This is standard practice for systems papers and
  avoids diluting the scientific claim.
- The experimental evidence (V0.4a, V0.5) belongs to the PM-1 architecture:
  both experiments test the packet architecture and handoff semantics, not the
  adapter.
- The technical note keeps the adapter documented, versioned, and citable
  without pretending it carries the scientific weight.
- Verdict: strongest scientific coherence.

### Recommendation

**PRIMARY = C**

- Main paper: *Pro Memoria: Skip-Based State Transmission for Long-Horizon
  Agent Handoffs* — PM-1 architecture + V0.4a + V0.5.
- Technical note (separate): *PM-Adapter: A Deterministic Schema Adapter for
  PM-1 State Transmission* — software artifact documentation.

If a second paper is later warranted, it should come only after a dedicated
adapter evaluation exists.

---

## 2. Scientific Contributions (smallest defensible set)

### Architectural contribution

- The organizing principle "skip, don't compress": known or unnecessary
  history is not retransmitted; the receiving worker receives the state
  required to continue.
- The architectural consequence: cumulative transmission cost is decoupled
  from accumulated history length.
- NOT claimed: inventing state handoff generally, inventing agent memory, or
  universal superiority over conversational memory.

### Protocol contribution

- PM-1 specifies a bounded continuation-state packet: the
  `sections → records → payload` shape, a fresh-worker handoff boundary, and
  digest-continuity integrity semantics.
- Encoding agnosticism: PM-1 is defined by what is transmitted and skipped,
  not by any encoding. Morse was the original encoding; V0.5 uses a PM-1-shaped
  JSON packet with the same architecture.

### Empirical contribution

- V0.4a (4,000 calls): PM-1 state survives 100 sequential handoffs across
  10 chains and 4 conditions with 0 protocol-induced drift, 100% state
  integrity, and 100% digest continuity; the single H-full failure was a model
  PARSE_ERROR, not a protocol failure.
- V0.5 (26,100 calls): measured approximately-linear cumulative transmission
  for the packet condition versus strongly super-linear cumulative growth for
  the accumulating-conversation condition over horizons 10–250; 90.43%
  cumulative-token reduction at H250; bounded per-hop packet context
  (~78–79 tokens) versus growing conversational context (up to ~8,864 tokens).

### System / implementation contribution

- PM-Adapter: a deterministic schema adapter separating PM-1 transport from
  domain schemas, with verification records. Reference implementation of the
  packet architecture; not part of the scientific claim.

### Evaluation of the central contribution

> "A handoff architecture that avoids retransmitting accumulated
> conversational history by transmitting bounded continuation state, with
> measured long-horizon token/context consequences."

This is the correct central claim, with one mandatory qualifier: the
measurements are over observed horizons 10–250, a single task family, a single
model, and synthetic deterministic scenarios. The claim is about the measured
consequence of the skip semantics, not a proof of asymptotic behavior and not a
general claim about all agent handoffs.

---

## 3. Claim Hierarchy

### SUPPORTED BY DATA

| Claim | Evidence |
|---|---|
| State survival | V0.4a: 100% state integrity, 100% digest continuity, 0 protocol-induced drift across 4,000 calls / 100-hop / 4 conditions. V0.5 P: 100% state integrity and 100% digest continuity across all 13,050 P hops. |
| State transmission (bounded) | V0.5 P per-hop context flat at ~78–79 tokens / 314–319 chars across H10–H250. |
| Token economics (measured) | V0.5 P cumulative approximately linear (R²=0.999998; power exponent 0.9946); C cumulative strongly super-linear (quadratic R²=0.999999; power exponent 1.6905); 90.43% cumulative-token reduction vs C at H250. |
| Fresh-worker continuation | Correct continuation actions from fresh workers receiving only packet + task spec across 26,100 calls in the benchmark's task family. |
| Failure taxonomy capture | 5 non-PASS records across 26,100 calls, classified (PARSE_ERROR ×3, ACTION_ERROR ×1, STATE_CORRUPTION ×1), none unclassified. |
| Encoding substitution (one instance) | Architecture operated with a JSON packet (V0.5), demonstrating Morse is not required for the architecture to function (single alternative encoding only). |

### PARTIALLY SUPPORTED

| Claim | Why partial |
|---|---|
| Language/encoding agnosticism | Supported for the two encodings tried (Morse in OG, JSON in V0.5); not a general claim over arbitrary encodings. |
| Digest continuity as integrity proxy | Valid within the benchmark's digest definition; not validated against external truth for all failure modes. |
| V0.4a H-full vs H-direct equivalence | 999/1,000 vs 1,000/1,000; the single PARSE_ERROR moved chain-survival 10 pp (9/10 vs 10/10). Equivalence holds on handoff success, is partial on chain survival due to one model formatting failure. |

### NOT TESTED

- Knowledge transmission (semantic content beyond continuation state)
- Institutional memory
- Evolving decisions and decision supersession
- Active knowledge selection
- Cross-model interoperability / heterogeneous-agent swarms
- Compacted or summarized conversation baselines
- Retrieval-based memory baselines
- Field-level delta skipping (V0.5 sends a bounded full-state snapshot)
- Full protocol envelope semantics (V0.5 packet is payload-shaped subset)
- Real-world cost savings (costs parameterized, not priced)

### OUT OF SCOPE

- Universal superiority over conversational memory
- Asymptotic O(N) vs O(N²) proof (measured growth only)
- Live-market / trading performance claims
- Production or clinical reliability guarantees
- "PM-1 prevents model failures"

---

## 4. Paper Outline (main paper, Option C)

1. Title
2. Abstract
3. Introduction
4. Problem formulation
5. Pro Memoria architecture
6. Skip semantics
7. PM-1 packet model
8. Relationship to conversational handoff
9. Experimental methodology
10. V0.4a state-survival experiment
11. V0.5 token/context experiment
12. Results
13. Failure taxonomy
14. Threats to validity
15. Discussion
16. Relationship to PM-Adapter
17. Limitations
18. Future work
19. Conclusion

(Split for the technical note: adapter design, schema, verification records,
integration — the main paper keeps only §16 as a pointer.)

---

## 5. Positioning

### The distinction that carries the paper

- **PM-1 is a handoff architecture, not a compression codec.** Compression
  operates on a message to make it smaller; PM-1 changes *what is transmitted*
  so that history is not transmitted at all. The 90.43% figure is the
  cumulative-token difference between two handoff strategies, never a
  compression ratio applied to history.
- **Why it matters technically:** compression inherits the input's growth —
  a compressed transcript still grows as the transcript grows. Skip semantics
  decouple transmission cost from history length; the packet stays bounded
  because history is dropped, not shrunk. The measured scaling separation
  (approximately linear vs strongly super-linear) is a consequence of this
  architectural choice, not of a better codec.
- **Morse = original encoding implementation; PM-1 = architecture.**
  Morse was chosen because the author found it elegant after seeing another
  project use Braille. Nothing in the protocol semantics depends on it.
  V0.5's use of a JSON packet under the same architecture is evidence for
  encoding agnosticism.
- **Precision requirement:** V0.5 exercised a PM-1-shaped state packet
  (payload-shaped subset of the canonical packet), not every feature of the
  full OG implementation (no envelope semantics, trivial selection, full-state
  snapshot, no Morse). These are scope boundaries, stated explicitly.

---

## 6. V0.4a → V0.5 Story

- V0.4a asks: *Can PM-1 state survive repeated sequential handoffs?*
  Answer: yes — 100% state integrity and digest continuity over 100 hops,
  4,000 calls, 0 protocol-induced drift.
- V0.5 asks: *What is the transmission/context cost of repeatedly handing off
  state while avoiding accumulated conversational history?*
  Answer: measured approximately-linear cumulative cost for the packet
  condition vs strongly super-linear for the accumulating-conversation
  condition; bounded per-hop context.
- Neither experiment tests institutional knowledge transmission. That is a
  later, explicitly separate experiment (§8).

---

## 7. PM-Adapter Decision

### Analysis

- **Integral to the scientific contribution?** No. The scientific claim is
  about the handoff architecture; V0.5 does not use PM-Adapter.
- **Merely the reference implementation?** It is a distinct software component
  (schema adapter with verification records), best described as the reference
  implementation of the packet architecture's decode/encode boundary.
- **Independently publishable as a full paper?** Not yet — no dedicated
  adapter evaluation exists.
- **Better presented as a software artifact?** Yes — repository, schema,
  verification records, technical note.
- **Separate technical paper?** Only after a dedicated adapter evaluation.

### Recommendation

Document as a software artifact + technical note. Do not force it into the
main paper.

- Title: *PM-Adapter: A Deterministic Schema Adapter for PM-1 State
  Transmission*
- Research question: How can PM-1 transport be cleanly separated from domain
  schemas so that domain schemas change without touching handoff semantics?
- Contribution: deterministic schema mapping, verification records, integration
  contract between PM-1 state layer and domain projections.
- Evaluation: adapter verification records + schema-fidelity checks
  ([CITATION NEEDED] for comparison points); no API experiment in the note.
- Relationship to PM-1 paper: the main paper cites the note as the reference
  implementation; the note cites the main paper for architecture and evidence.

---

## 8. Future Work (next experimental phase)

### Question

> Can a bounded handoff packet preserve the CURRENT institutional truth when
> knowledge changes over time?

### Must add (relative to V0.5)

- Evolving decisions with supersession semantics (stable `decision_id`,
  `supersedes`, `effective_tick`)
- Active knowledge selection: the packet carries the currently-active set, not
  merely the most recent records
- Taxonomy changes (definitions that update)
- Detector / validation logic changes
- Fresh workers applying the latest institutional truth
- Ideally heterogeneous models later; single model first

### Why this is the next experiment

V0.5 transmits 2–3 state integers; there was no selection problem. The next
experiment makes selection load-bearing: when the institutional truth changes,
does a fresh worker acting only on the packet act on the current version rather
than a superseded one? This directly addresses the "integer relay race"
criticism. It must be framed as a new experiment, not a reinterpretation of
V0.5.

---

## 9. Claims That MUST NOT Appear in Either Document

1. "PM-1 compresses history by 90%" / "90% compression" / "90% memory
   compression."
   → Correct form: "90.43% cumulative-token reduction relative to the
   accumulating conversational condition at H250."
2. "PM-1 had 100% success" / "100% success rate."
   → Correct form: "PM-1 maintained 100% state integrity and digest continuity
   across all P hops; 99.98% of P hops produced successfully formatted worker
   responses; the three PARSE_ERROR events produced no state divergence."
3. "PM-1 invented state handoff" or "invented agent memory."
4. "PM-1 preserves conversational knowledge."
5. "Asymptotically proven O(N) vs O(N²)."
   → Correct form: "measured approximately-linear vs strongly super-linear
   growth over observed horizons."
6. "PM-1 prevents model failures."
7. "PM-1 outperforms compacted/summarized conversation" (no such baseline ran).
8. "PM-1 outperforms retrieval-based memory" (no such baseline ran).
9. "Cross-model generalization demonstrated" (single model: deepseek-v4-flash).
10. "Institutional knowledge transmission demonstrated" (not tested).
11. "Field-level delta skipping demonstrated" (bounded full-state snapshot was
    used).
12. "Full PM-1 protocol envelope exercised" (payload-shaped subset).
13. "Morse defines PM-1" / "Morse is required."
14. "Universal superiority over conversational memory."
15. "Real-world cost savings measured" (cost parameterized, not priced).
16. Any live-market or trading-performance claim.

---

## 10. Recommended Titles / Abstract / Next-Experiment Title

### Primary paper title

*Pro Memoria: Skip-Based State Transmission for Long-Horizon Agent Handoffs*

### Recommended abstract

See the paper draft (Part 2 of this package) for the full abstract.

### Next experiment title

*Can a Bounded Handoff Packet Preserve Current Institutional Truth Under
Evolving Decisions?*

---

## 11. Confirmation

- API calls = 0 (none made during this design task)
- Experiment executions = 0
- Raw V0.5 artifacts modified = 0 (no files under results/v0.5 touched)
- H500/H1000 executed = NO (remain registered, unexecuted; 90,000 calls
  remain unexecuted)
