# PM-1 V0.5 — Public README (draft)

> Public-facing reproduction README. Path-neutral; raw data download
> instructions point to the Zenodo record (DOI placeholder). This is a draft
> for the future `pm1-v05/` release root — do not publish until the release
> checklist (see RELEASE_READINESS_REPORT.md) is complete.

---

## Overview

**PM-1 (Pro Memoria)** is a handoff architecture for sequential agent
workflows, organized around a single principle:

> **SKIP, DON'T COMPRESS.**

PM-1 is a handoff architecture, not a compression codec. Compression
represents the same accumulated information more compactly. PM-1 changes what
crosses the handoff boundary: information that is already known or unnecessary
for continuation does not cross it. Each fresh worker receives a bounded
continuation-state packet — the state required to continue — rather than the
accumulated conversational history of its predecessors.

The architecture is designed to be encoding-agnostic. The original
implementation used Morse; this benchmark uses a PM-1-shaped JSON packet.
Morse is the original encoding implementation, not the definition of PM-1.

## Experiment

**V0.5** compared two handoff conditions on the same deterministic synthetic
portfolio/state task:

- **Condition P (bounded state packet):** each worker receives a bounded PM-1
  continuation-state packet plus the immutable task specification.
- **Condition C (accumulating conversation):** each worker receives the
  chronological transcript of all prior (state → action) entries plus a
  current-state line, plus the same immutable task specification.

Both conditions use the same model, task, initial state, schedule,
temperature, maximum output tokens, oracle, and success criteria. Workers run
in **fresh contexts every hop**; the worker never sees its condition, the
horizon, the trial, the scenario, the seed, the expected action, the oracle
output, or token counts. The task has a **deterministic oracle** and
controlled state transitions, so state divergence is measurable per hop.

Horizon structure: H10, H25, H50, H100, H250 — all prefixes of the same master
chain specification. Each horizon runs 10 scenarios × 3 trials × 2 conditions.

## Executed scope

| Item | Value |
|---|---|
| Registered calls | 116,100 |
| **Executed calls** | **26,100** |
| Completed horizons | H10, H25, H50, H100, H250 |
| Not executed | H500, H1000 |
| Unexecuted registered calls | 90,000 |

The full 116,100-call registration was **not** completed. Execution was
intentionally stopped after H250, which produced sufficient evidence for the
scoped V0.5 conclusion. H500 and H1000 are registered but unexecuted; no
results exist for them and none are claimed.

## Results (H250)

- P cumulative tokens: **3,672,305**
- C cumulative tokens: **38,366,105**
- Cumulative-token reduction: **90.43% relative to the accumulating
  conversational condition** (this is a difference between two handoff
  strategies, not a compression ratio)

### Reliability (P condition, 13,050 hops)

- **99.98%** successfully formatted worker responses
- **100%** state integrity
- **100%** digest continuity
- 3 PARSE_ERROR records, all with zero state divergence

Worker formatting success and state integrity are distinct measurements and
are reported separately. A malformed response is a worker-output failure;
state divergence is an integrity failure.

## Reproduction

### Offline reproduction (no API, no credentials)

1. Install dependencies (see `requirements.txt`; small Python stdlib +
   `requests`/`urllib` surface, `pytest` for tests).
2. Run the offline test suite: `pytest tests/`
3. Inspect experiment definitions: `task-spec.json`, `results/v0.5/
   V0.5_PREEXPERIMENT_REPORT.md`, `results/v0.5/V0.5_PILOT_CONFIG.md`,
   `ARCHITECTURE.md`.
4. Regenerate derived analysis from raw records (raw records are archived on
   Zenodo — see below; the reproduction manifest lists every file and its
   SHA-256 hash).

### API-backed experiment reproduction

Reproducing the experiment itself requires provider credentials and paid API
calls. It is **not** free, and it does **not** require running H500/H1000.
The benchmark harness is in `benchmark/` (`run_v05a_*.py`,
`runner.py`, `lib/`). Credentials are read from environment variables or a
local credential file that is **excluded** from this repository.

### Raw data

The large raw artifacts (V0.5 checkpoint and hop records, V0.4a hop records)
are archived on Zenodo: **DOI placeholder**. The repository contains the
reproduction manifest with file hashes, the hop-record schema, and download
instructions (see `data/README.md`).

## Status documents

- `results/v0.5/EXPERIMENT_STATUS.md` — registered vs executed matrix, stop
  reason
- `results/v0.5/V0.5_POST_H250_CONSOLIDATION_REPORT.md` — consolidated
  results

## Scope / non-claims

V0.5 demonstrates bounded continuation-state handoff against an accumulating
conversational transcript in this benchmark. It does **not** demonstrate:
heterogeneous-state selection, budgeted semantic selection, institutional
knowledge preservation, decision supersession, retrieval, compaction, or
heterogeneous models. Those are the subject of the next research phase.

## License

Code: [MIT / Apache-2.0 — per LICENSE]. Data: CC BY 4.0. Paper: see LICENSE.

## Citation

See `CITATION.cff`.
