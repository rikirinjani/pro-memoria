# PM-1 Paper — Final Pre-Submission Audit

Auditor role: OG PM-1 architect + skeptical systems-paper reviewer.
Audited manuscript: `PM1_PAPER_DRAFT_R1.md` → revised as `PM1_PAPER_DRAFT_FINAL.md`.
Governing documents: `PM1_PUBLICATION_DESIGN.md`, `PM1_REVISION_R1_SUPPORTING.md`.
No experiments run; no API calls; no raw artifacts modified.

---

## 1. Related-Work Matrix

See `PM1_RELATED_WORK_BIB.md` for full entries. Summary:

| Work | Area | Relationship to PM-1 | Difference | Threat |
|---|---|---|---|---|
| MemGPT (2023) | agent memory | adjacent (memory placement) | pages history in/out; PM-1 drops history at handoff | no |
| Generative Agents (2023) | agent memory | adjacent (persistent store + retrieval) | keeps experience record; PM-1 never carries it | no |
| Lost in the Middle (2024) | long-context limits | motivating evidence | studies context use; PM-1 avoids accumulating | no |
| RAG (2020) | retrieval memory | future-work baseline | retrieves relevant content; PM-1 transmits canonical state | no |
| Blackboard (1983–86) | shared structured state | conceptual precedent | global shared state among active K-sources vs sequential handoff boundary | partial — sharpens novelty claim |
| LLMLingua (2023) | compaction | compression comparator | same info smaller; PM-1 changes what crosses | no |
| AutoGen (2023) | multi-agent handoff | adjacent | conversational message passing; PM-1 sends bounded state packet | no |
| StreamingDialogue (2024) | compaction | compression comparator | in-attention KV compression; PM-1 boundary-level skip | no |

---

## 2. Novelty / Prior-Art Assessment

**Question asked:** what is the narrowest defensible novelty claim?

**Facts:** state-based handoff, structured agent state, memory records,
summarization, truncation, retrieval, delta updates, event sourcing,
checkpointing, session state, and protocol-level handoff all exist in prior
work. PM-1 does NOT claim any of these are new.

**Distinction that survives scrutiny:**

> PM-1 formalizes the handoff boundary as a selective transmission boundary —
> accumulated conversational history is intentionally not retransmitted — and
> empirically evaluates bounded continuation-state transmission against
> accumulating conversational history across repeated fresh-worker handoffs.

**Verdict:** defensible, with two guardrails the paper already carries:
(1) the blackboard line must state explicitly that structured shared state is
not new — the contribution is the handoff-boundary formalization and its
measured token consequence, not structured state per se; (2) no claim of
universal superiority over compaction/summarization/retrieval, none of which
were tested. The claim is about a specific mechanism and a specific measured
comparison.

---

## 3. Numerical Audit

All numbers below were re-verified against the V0.5 Post-H250 Consolidation
Report and the V0.4a full report (read in full during this audit).

### V0.4a — all verified ✓
- 4,000 calls; 10 chains; 100 hops; 4 conditions (H-full, H-direct, H-corrupt,
  H-recover) ✓
- 100% state integrity every condition ✓; 100% digest continuity (H-full,
  H-direct) ✓; zero protocol-induced drift ✓
- H-full 999/1,000; single failure = model PARSE_ERROR (chain-05, hop 24),
  no state consequence ✓
- H-corrupt also had 1 PARSE_ERROR (chain-08, hop 40) — present in source
  report; the final manuscript mentions the H-full PARSE_ERROR as the primary
  and the H-corrupt one as a second model formatting failure for accuracy.

### V0.5 — all verified ✓
- 26,100 calls = 13,050 P + 13,050 C ✓
- Horizons 10/25/50/100/250 with call counts 600/1,500/3,000/6,000/15,000 ✓
- Cumulative totals (P / C / reduction): H10 149,590 / 168,676 / 11.32%;
  H25 370,703 / 633,117 / 41.45%; H50 737,870 / 1,957,375 / 62.30%;
  H100 1,474,888 / 6,819,750 / 78.37%; H250 3,672,305 / 38,366,105 / 90.43% ✓
- P per-hop context 78–79 tokens / 314–319 chars, bounded ✓
- C max 8,864 tokens / 35,457 chars at H250 ✓
- P scaling: linear R²=0.999998, power exponent 0.9946 ✓
- C scaling: quadratic R²=0.999999, linear R²=0.960105, power exponent 1.6905 ✓
- P reliability: 99.98% formatted responses; 100% state integrity; 100% digest
  continuity; 3 PARSE_ERROR; 0 P divergence ✓ (not collapsed into "100%
  success")
- Aggregate: 5 non-PASS (3 PARSE_ERROR, 1 ACTION_ERROR, 1 STATE_CORRUPTION);
  the ACTION_ERROR and STATE_CORRUPTION occurred under C at H100, scenario 8,
  trial 2, hops 2–3; the three H250 parse errors (C hop 79, P hop 102, P hop
  188) had zero divergence ✓

### Failure taxonomy — verified ✓
Exactly the five records, correctly attributed by condition, horizon, and
scenario/trial/hop. The manuscript does not imply P prevents model errors,
does not attribute C's failures to the protocol, and does not treat parse
errors as state corruption.

---

## 4. Claim-Boundary Audit

| Claim | Classification | Manuscript status |
|---|---|---|
| Sequential state survival | SUPPORTED | stated with 100% integrity/continuity ✓ |
| Bounded state transmission | SUPPORTED | ~78–79 tokens/hop, bounded ✓ |
| Bounded handoff context | SUPPORTED | P flat across H10–H250 ✓ |
| Token economics vs C | SUPPORTED | 90.43% cumulative-token reduction relative to C at H250 ✓ |
| Approximately-linear P / super-linear C | SUPPORTED (measured) | hedged as measured, not asymptotic ✓ |
| State integrity / digest continuity | SUPPORTED | separated from formatting success ✓ |
| Failure capture/classification | SUPPORTED | taxonomy table ✓ |
| Encoding agnosticism | PARTIAL | "designed to be agnostic; broader validation remains" ✓ |
| Digest as integrity proxy | PARTIAL | benchmark-scoped ✓ |
| H-full vs H-direct equivalence | PARTIAL | handoff-level; survival moved by 1 PARSE_ERROR ✓ |
| Knowledge transmission | NOT TESTED | explicitly out ✓ |
| Institutional memory / evolving decisions / supersession / active selection | NOT TESTED | explicitly out ✓ |
| Retrieval / compaction / summarization superiority | NOT TESTED | explicitly out (no baselines) ✓ |
| Cross-model / cross-provider / heterogeneous agents | NOT TESTED | explicitly out (single model) ✓ |
| Real-world monetary savings | NOT TESTED | cost parameterized ✓ |
| Universal superiority | OUT OF SCOPE | refused ✓ |
| Asymptotic O(N)/O(N²) proof | OUT OF SCOPE | refused (measured language) ✓ |
| Live trading / production reliability | OUT OF SCOPE | refused ✓ |
| "90% compression" | FORBIDDEN | absent; correct phrasing used throughout ✓ |

---

## 5. Baseline Fairness Audit

- P: bounded PM-1 packet. C: accumulating transcript + current state.
- Same model, task, initial state, schedule, temperature, max tokens, oracle,
  success criteria. Fresh context per hop. Worker never told condition/horizon/
  trial/scenario/seed/expected action/token counts. ✓
- C is explicitly labeled a naive accumulating baseline. ✓
- No compaction, summarization, retrieval, or external-memory baseline —
  disclosed in Methodology, Threats, and Limitations. ✓
- Neither hidden nor over-weakened: the measured result (90.43% relative to
  the tested C condition) stands exactly as measured, and the boundary is
  stated. ✓

---

## 6. Scaling-Claim Audit

- P linear R²=0.999998, power 0.9946; C quadratic R²=0.999999, linear
  R²=0.960105, power 1.6905 — all present verbatim ✓
- Language used: "approximately linear versus strongly super-linear growth
  over the measured horizons H10–H250"; "closely fit by a quadratic model" ✓
- No "O(N)" / "O(N²)" / "proven complexity" statements ✓
- H500/H1000 stated as registered but not executed; no extrapolation, no
  implication of failure ✓
- The five measured horizons are the evidence; no asymptotic claim ✓

---

## 7. Reviewer Attack Simulation

Ten strongest fair criticisms, with disposition (revise / limitation / scope):

1. **"C is a strawman; practical systems use compaction/summarization/retrieval."**
   — Valid. Already addressed: C is labeled naive; no compaction/summarization/
   retrieval baseline exists; the paper bounds the claim to "relative to the
   accumulating conversational condition tested." (limitation, disclosed)
2. **"Isn't PM-1 just structured state serialization?"**
   — Partially valid. Structured state is not new (blackboard precedent).
   Addressed in final manuscript Discussion: the contribution is the selective
   handoff boundary (what crosses), plus measured transmission consequences —
   not the existence of structured state. (revision — added explicit contrast)
3. **"Isn't 'skip' just choosing a smaller state representation?"**
   — Partially valid. Addressed: PM-1 selects a bounded continuation state;
   the mechanism claim is about not retransmitting accumulated history across
   fresh-worker boundaries, which the C comparison isolates. The paper does
   not claim novelty for state selection itself. (revision — clarifying
   sentence in Discussion)
4. **"Single model, single task family, temperature 0, synthetic task."**
   — Valid. Disclosed; explicitly NOT TESTED. (limitation)
5. **"Trivial state; no semantic knowledge — is this just an integer relay?"**
   — Valid. Disclosed; the knowledge-transmission question is the defined next
   experiment, not claimed here. (limitation + future work)
6. **"Full-state snapshot; no delta/field-level selection."**
   — Valid. Listed as implementation scope boundary (1 of 4). (limitation)
7. **"Encoding agnosticism unproven beyond two encodings."**
   — Valid. Wording restricted to "designed to be agnostic… broader validation
   remains." (limitation)
8. **"Scaling extrapolation: five horizons, no H500/H1000."**
   — Valid. Registered-but-unexecuted stated; measured language only.
   (limitation)
9. **"Token accounting: provider usage vs chars/4 heuristic."**
   — Valid. Provider usage preferred; heuristic used and reported explicitly
   when usage omitted; token-completeness 26,100/26,100. (disclosed)
10. **"Attention dilution vs context capacity not measured."**
    — Partially valid and out of scope: V0.5 measures transmission/context
    economics, not model attention behavior; Lost in the Middle is cited as
    motivating evidence that long context is not free. (scope — stated)

Disposition summary: 3 items led to clarifying revisions (2, 3, and the
blackboard contrast); all others are disclosed limitations or explicit scope
boundaries. No valid criticism was hidden.

---

## 8. Venue Recommendations

**A. Systems / infrastructure venues**
- **arXiv cs.SE / cs.DC / cs.AI preprint** — first stop; reproducible
  benchmark + clean claim boundary suits preprint-first practice. Mature
  enough now.
- USENIX/ICML systems tracks — only after a compaction/summarization baseline
  and a second model are added. Not yet.

**B. AI agents / multi-agent venues**
- **Workshops on LLM agents (NeurIPS/ICLR/ICML agent workshops)** — strong
  fit; the fresh-worker handoff question is an agent-architecture question.
  Mature enough with current evidence; a workshop submission after one
  additional baseline is realistic.

**C. Applied ML venues**
- Not primary; the paper is architectural/empirical rather than method-
  improvement oriented. Only if reframed around a benchmark contribution.

**D. Workshop / short-paper venues**
- **COLM / ACL / EMNLP workshop track** — viable short-paper target: bounded
  state handoff + token economics is a compact, defensible workshop claim.

Recommended immediate path: arXiv preprint (cs.AI), then an LLM-agent
workshop submission. A full-venue journal/conference submission should wait
for the baseline extension (compaction vs summary vs retrieval) and ideally a
second model. Acceptance likelihood cannot be predicted and is not claimed.

---

## 9. Remaining Issues

1. **Two verified second-model/baseline gaps** are the only substantive
   requirements before a strong full-venue submission: (a) at least one
   compaction/summarization baseline, (b) at least one additional model.
2. Related-work slots remain for: formal agent-handoff taxonomies, stateful-
   agent surveys, and a direct "state-not-conversation transmission" empirical
   study — none verified; kept as [CITATION NEEDED] rather than fabricated.
3. The HackerNoon practitioner article is adjacent evidence only; if cited,
   it must be marked non-academic with a captured URL.

---

## 10. Audit Conclusion

The R1 manuscript survives the audit with three clarifying revisions (all
applied in `PM1_PAPER_DRAFT_FINAL.md`): the structured-state-serialization
contrast, the skip-vs-smaller-representation clarification, and the explicit
blackboard/novelty boundary. All numbers verified. All claim boundaries
maintained. The paper is internally consistent, honest about its baselines,
and ready for external peer review at the preprint/workshop level as scoped.
