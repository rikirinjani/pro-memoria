# PM-1 Project State Update — V0.6 Wrapped / V0.7 Parked / V0.7-C Forked

Date: 2026-08-21. Documentation/state-management task only.

---

## V0.5 — ESTABLISHED / FROZEN

Released as v0.5.0. GitHub: https://github.com/rikirinjani/pro-memoria.
Zenodo: https://doi.org/10.5281/zenodo.22005884.

- 26,100 completed API-backed handoffs, H10–H250
- 90.43% cumulative-token reduction vs accumulating conversational condition
- 99.98% formatted responses; 100% state integrity; 100% digest continuity
- H500/H1000 registered but NOT executed

V0.5 is frozen. Do not modify.

---

## V0.6 — WRAPPED / FROZEN

V0.6 is officially WRAPPED. Do not reopen unless a future authorized experiment requires returning to one of its deferred questions.

### What V0.6 established

1. **PM-1 action-equivalence is a real observable phenomenon** in the controlled state-transition experiment.
2. **Budget affects action-equivalence** — the adapter's budget-constrained selection produces field omissions that the model cannot recover from.
3. **Relevance density ≠ state sufficiency ≠ action-equivalence** — these are distinct phenomena; higher density does not guarantee correct continuation.
4. **Action-equivalence boundary is trajectory-dependent** — different seeds/modes produce different boundaries.
5. **Mode is causally implicated** — the controlled seed33 step→lazy crossing showed mode changes alter action-equivalence (100% PASS → 10% PASS).
6. **Mode × trajectory interaction is supported** — step helps seed33 but not seed11; the effect is asymmetric.
7. **Structural differential** — the adapter transmits identical field structures while model behavior differs; the differential is in the model's interpretation, not in adapter field omission.
8. **PM-1's useful-state selection and action-equivalence are distinct phenomena** — should not be collapsed into a single "density" metric.

### EMPTY handling

- EMPTY is NOT a semantic action-equivalence outcome.
- MiMo EMPTY behavior investigated through raw-response capture, h10/h25 diagnostics, runner-chain, and session-position diagnostics.
- A session-position phenomenon was observed (sharp cliff after ~15 sequential calls).
- The provider-side mechanism remains unresolved.
- EMPTY remains excluded from semantic action-equivalence conclusions unless explicitly reopened.

### Epistemic discipline

The following remain unresolved/deferred:

1. Exact causal mechanism by which mode affects behavior.
2. Complete independent separation of mode vs trajectory effects.
3. Full numeric/trajectory isolation.
4. Ultimate mechanism of MiMo EMPTY/session behavior.

These do NOT block V0.6 closure. V0.6 is described as "mechanistically characterized enough to establish the core action-equivalence phenomenon and its major observed determinants; remaining mechanism-level questions are explicitly deferred."

---

## V0.7 — PARKED

V0.7 is officially PARKED. Not the active execution line.

The numeric-snapshot result became inconclusive as a semantic sufficiency test: the EMPTY outcome could not be treated as a semantic selection failure (EMPTY is a generation phenomenon, not a selection failure).

V0.7 is not "failed" and not "fully solved." It is PARKED with its unresolved questions preserved.

### V0.7 Deferred Questions Register

| # | Question | Status |
|---|---|---|
| DQ1 | Exact causal mechanism by which mode affects behavior | Open — raw evidence insufficient |
| DQ2 | Complete independent separation of mode vs trajectory effects | Partially addressed (seed33 crossing done; seed11 isolation pending) |
| DQ3 | Full numeric/trajectory isolation (numeric injection test) | INVALIDATED as semantic test (snapshot ≠ trajectory) |
| DQ4 | Trajectory-level properties beyond numeric snapshot values | Unknown — snapshot injection did not reproduce trajectory behavior |
| DQ5 | Provider/session EMPTY mechanism | Open — session-position artifact identified; provider-side mechanism unresolved |

---

## V0.7-C — NEW ACTIVE BRANCH: Capability Boundary / External Validation

This is a NEW research direction — not a continuation of V0.7's microscopic questions.

### Central hypothesis

> For a fixed model and task environment, PM-1 may preserve or increase the amount of the model's problem-solving capability that remains expressible through an agentic system under constrained state/context conditions, relative to a competent conventional state-management architecture.

### Key principles

- Model identity is NOT the theory. Luna, MiMo, DeepSeek V4, and other models may serve as replication axes.
- The object of study is the STATE ARCHITECTURE / BOUNDARY, not a particular model.
- DeepSWE is a proving ground, not the definition of PM-1.

### L0–L4 Capability Ladder

| Level | Configuration | Purpose |
|---|---|---|
| L0 | Model alone (no tools/skills/memory/orchestration) | Estimate intrinsic task capability |
| L1 | Model + supplied context | Understand capability with controlled context |
| L2 | Model + tools | Separate tool-enabled from memory/state effects |
| L3 | Conventional agent (competent state management) | Measure capability under conventional architecture |
| L4 | PM-1 agent | Measure capability under PM-1 state architecture |

Principal causal comparison: **L3 vs L4 under matched conditions.**

L0–L2 are capability/context baselines, not direct PM-1 treatment comparisons.

### State pressure requirement

V0.7-C must contain a predefined pressure ladder (comfortable → mild → moderate → high → extreme). Pressure levels must be calibrated in Phase 1 and frozen before Phase 2. A null result at comfortable pressure is not a failure — it may be expected if state is abundant.

### Fair L3 baseline

L3 must use a competent conventional strategy: sliding/recent context, structured summarization at threshold, preservation of task state/decisions/unresolved issues/tool results/code references. The baseline must represent what a competent practitioner would deploy. Do NOT use naive history truncation. Do NOT tune L3 against PM-1 after seeing Phase 2 results.

### Fair L0 construction

L0's supplied context must be principled and mechanical — not human-knowledge-dependent. Phase 1 must establish and validate the rule (e.g., task statement + failing test + directly referenced symbols; bounded repository dependency closure; or another deterministic rule). Frozen before Phase 2.

### Phase structure

- **Phase 1 — Calibration:** no confirmatory "PM-1 wins" claim. Establish reproducible L0/L3/L4, task difficulty variance, appropriate pressure levels, runtime/token cost, execution and evaluation reliability, suitable benchmark subset, sample size. Results used to design the powered pilot.
- **Phase 2 — Powered Pilot:** frozen before execution — tasks, models, L0 rule, L3 strategy, L4 config, pressure levels, endpoints, statistical/decision procedure, negative-result criterion. Compare L3 vs L4 across predefined pressure ladder.
- **Phase 3 — External Validation:** after Phase 2; potentially larger DeepSWE subset, full DeepSWE, another external benchmark, another task domain, additional model replication.

### Pre-registered negative result rule (NON-NEGOTIABLE)

If PM-1 and the frozen conventional baseline are statistically indistinguishable: report a null result. Do NOT tune PM-1 until it wins, change pressure levels after seeing outcomes, replace difficult tasks, change the baseline after seeing outcomes, selectively remove unfavorable tasks, or redefine the endpoint.

### Model axis

The model is a replication/generalization axis, not the theory. Potential models: Luna, MiMo, DeepSeek V4, other reasoning models. The core comparison is same model + same task + same environment + same pressure + L3 vs L4.

### DeepSWE role

External validation environment, not the definition of PM-1. Start with a small calibration subset, estimate variance, run powered pilot, then larger external validation.

---

## V0.8–V1.0 Trajectory

- **V0.8:** Generalization across models/tasks/environments after V0.7-C.
- **V0.9:** Stabilize PM-1 as a model-agnostic state-transition architecture.
- **V1.0:** Demonstrate, with reproducible evidence, that PM-1 preserves or increases expressed problem-solving capability under constrained agentic state relative to competent conventional state management. DeepSWE is one external proving ground, not the definition.

---

## Current Project State Summary

| Version | Status |
|---|---|
| V0.5 | ESTABLISHED / FROZEN |
| V0.6 | WRAPPED / FROZEN |
| V0.7 | PARKED (deferred questions register maintained) |
| V0.7-C | NEW ACTIVE DESIGN BRANCH |
| V0.8 | FUTURE |
| V0.9 | FUTURE |
| V1.0 | FUTURE |
