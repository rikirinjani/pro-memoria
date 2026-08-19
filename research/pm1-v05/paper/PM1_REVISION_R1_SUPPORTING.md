# PM-1 Paper — Revision R1 Supporting Document

Governing document: `PM1_PUBLICATION_DESIGN.md`.
Revision of: `PM1_PAPER_DRAFT.md` → `PM1_PAPER_DRAFT_R1.md`.
Date: 2026-08-18. No experiments run; no API calls; no raw artifacts modified.

---

## A. Revised Publication Design Summary

- **PRIMARY = Option C, unchanged.** One scientific paper — *Pro Memoria:
  Skip-Based State Transmission for Long-Horizon Agent Handoffs* — covering
  the PM-1 architecture, the skip-don't-compress principle, V0.4a, and V0.5.
- **PM-Adapter stays a separate software artifact / technical note.** It was
  not the experimental variable in V0.5 and is not the basis of the V0.5
  scientific claim. The main paper contains only a concise relationship
  section (§16).
- **Central anchor, preserved verbatim:** *skip, don't compress* — PM-1 is a
  handoff architecture, not a compression codec. Compression transmits the
  same accumulated information in a smaller representation; PM-1 changes what
  crosses the handoff boundary so that known or unnecessary history is not
  transmitted at all.
- **Encoding position, revised:** Morse is the original encoding implementation
  and part of the architecture's provenance; PM-1 is the architecture. The
  successful substitution of JSON demonstrates Morse is not required by the
  architecture; broader encoding agnosticism remains to be evaluated.
- **Scope, sharpened:** V0.5 tests state survival, state transmission, bounded
  context, and token economics. It does not test semantic knowledge
  transmission, institutional memory, evolving decisions, decision supersession,
  or active knowledge selection — those are future work.
- **Experimental history preserved:** H500 and H1000 were registered but not
  executed; they did not fail and no results are extrapolated for them. Scaling
  characterizations cover H10–H250 only.

---

## B. Revised Paper Outline

1. Title
2. Abstract
3. Introduction (research question; skip vs compress stated up front)
4. Related Work ([CITATION NEEDED] placeholders only)
5. Problem Formulation (P vs C; scope to state transmission)
6. Design Goals (boundedness, continuation, integrity)
7. Pro Memoria Architecture (4 concerns; ARCHITECTURE.md pointer)
8. Skip Semantics (skip vs shrink; scope boundaries of the implementation)
9. PM-1 Packet Model (packet shape; digest; encoding section)
10. Relationship to Conversational Handoff (fairness; baseline boundary)
11. Experimental Methodology (task; model; token/context measurement;
    horizons; scaling analysis; reliability metrics; acceptance criteria)
12. V0.4a — State-Survival Experiment
13. V0.5 — Token/Context Scaling Experiment
14. Results (cumulative totals; per-hop context; scaling; reliability;
    formatting-success vs state-integrity distinction)
15. Failure Taxonomy
16. Threats to Validity
17. Discussion (mechanism; reliability; claim boundary)
18. Relationship to PM-Adapter
19. Limitations
20. Future Work
21. Conclusion

Note: the previous draft's §4 ("Problem Formulation and Design Goals") was
split into §5 Problem Formulation and §6 Design Goals; the outline now numbers
21 sections, with Related Work moved before Problem Formulation (systems-paper
convention).

---

## C. Full Revised Manuscript

`PM1_PAPER_DRAFT_R1.md` — full text, submission-oriented.

---

## D. "Claims to Avoid" Checklist

These MUST NOT appear in either the paper or the technical note:

1. "PM-1 compresses history by 90%" / "90% compression" / "memory compression"
   / "compressed history" / "compression ratio."
   → Correct: "90.43% cumulative-token reduction relative to the accumulating
   conversational condition at H250."
2. "PM-1 had 100% success" / "100% success rate."
   → Correct: "PM-1 maintained 100% state integrity and digest continuity
   across all 13,050 P hops, while 99.98% produced successfully formatted
   worker responses; the three PARSE_ERROR events produced no state
   divergence."
3. "PM-1 invented state handoff" or "invented agent memory."
4. "PM-1 preserves conversational knowledge."
5. "Asymptotically proven O(N) vs O(N²)."
   → Correct: "measured approximately-linear vs strongly super-linear growth
   over the observed horizons H10–H250."
6. "PM-1 prevents model failures."
7. "PM-1 outperforms compacted/summarized conversation" (no baseline ran).
8. "PM-1 outperforms retrieval-based memory" (no baseline ran).
9. "Cross-model or cross-provider generalization demonstrated" (single model:
   deepseek-v4-flash).
10. "Institutional knowledge transmission demonstrated" (not tested).
11. "Field-level delta skipping demonstrated" (bounded full-state snapshot).
12. "Full PM-1 protocol envelope exercised" (payload-shaped subset).
13. "Morse defines PM-1" or "Morse is required."
14. "Universal superiority over conversational memory."
15. "Real-world monetary savings measured" (cost parameterized, not priced).
16. Any live-trading or trading-performance claim.
17. "Revolutionary," "solves," "eliminates," "proves" (marketing register).
18. "H500/H1000 failed" or "H500/H1000 completed" (they were registered but not
    executed).
19. "V0.5 tested intelligent memory selection" (selection was trivial).

---

## E. PM-Adapter Technical-Note Boundary

- **Title:** *PM-Adapter: A Deterministic Schema Adapter for PM-1 State
  Transmission* (technical note / software artifact).
- **Contents:** adapter design; schema mapping; verification records;
  integration contract between the PM-1 state layer and domain projections.
- **Non-contents:** no API experiment; no new benchmark; no scientific claim
  about handoff economics.
- **Relationship:** the main paper cites the note as the reference
  implementation of the transport/schema boundary (§16); the note cites the
  main paper for architecture and evidence.
- **Description used in the paper:** "PM-Adapter is a deterministic schema
  adapter separating PM-1 transport semantics from domain schemas. It is
  documented separately as a software artifact and technical note."

---

## F. Recommended Future-Experiment Paragraph

> The next experimental phase addresses the "integer relay race" criticism
> directly. Its question: *Can a bounded handoff packet preserve the CURRENT
> institutional truth when knowledge changes over time?* The phase must add,
> relative to V0.5: stable decision IDs; decision supersession; effective
> ticks; active knowledge selection (the packet carries the currently-active
> set, not merely the most recent records); taxonomy evolution; detector and
> validation logic evolution; and fresh workers applying the current
> institutional truth. Heterogeneous models should be introduced in a later
> phase, not retroactively claimed. This is a new experiment. It must not be
> presented as a reinterpretation of V0.5, and the V0.5 paper does not claim
> to have answered it.

---

## Verification

- API calls = 0
- Experiment executions = 0
- H500/H1000 executed = NO (registered, unexecuted; 90,000 calls remain
  unexecuted)
- Raw experiment artifacts modified = 0 (no files under results/ touched;
  only new files under paper/ created)
