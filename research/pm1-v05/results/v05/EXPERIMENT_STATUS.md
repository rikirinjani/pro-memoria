# V0.5 — Experiment Status

Status: public-facing status document for the PM-1 V0.5 benchmark.
Date: 2026-08-19.

## Registered vs executed

| Item | Value |
|---|---|
| V0.5 registered matrix (calls) | 116,100 |
| **Completed** | **26,100** |
| Unexecuted (registered, not run) | 90,000 |

## Horizons

| Horizon | Status |
|---|---|
| H10 | completed |
| H25 | completed |
| H50 | completed |
| H100 | completed |
| H250 | completed |
| H500 | registered, NOT executed |
| H1000 | registered, NOT executed |

## Why execution stopped

H250 produced sufficient evidence for the scoped V0.5 conclusion (bounded
continuation-state transmission vs accumulating conversational history, with
reliability and token-economics measurements). Execution was **intentionally
stopped before H500/H1000**.

This is a deliberately bounded experimental result, not a failed or
incomplete experiment. No results exist for H500/H1000, and none are claimed.
The measured scaling characterizations cover H10–H250 only.

## Data provenance

- 26,100 completed API calls (13,050 P + 13,050 C)
- 10 scenarios × 3 trials × 2 conditions at each of the five executed
  horizons
- Hop records: 26,100 / 26,100 persisted; checkpoint matches hop records;
  0 duplicate call IDs; 0 missing call IDs; 0 recomputed digest mismatches
- 5 non-PASS records across the full dataset (3 PARSE_ERROR, 1 ACTION_ERROR,
  1 STATE_CORRUPTION); the two state-related failures occurred in condition C
  at H100; all three H250 parse errors had zero state divergence

## Key result (H250)

- P = 3,672,305 cumulative tokens
- C = 38,366,105 cumulative tokens
- **90.43% cumulative-token reduction relative to the accumulating
  conversational condition**

## Reliability (P condition)

- 99.98% successfully formatted worker responses
- 100% state integrity
- 100% digest continuity
- 3 PARSE_ERROR, 0 state divergence

## Related artifacts

- `results/v0.5/V0.5_POST_H250_CONSOLIDATION_REPORT.md` — full consolidation
- `results/v0.5/V0.5_PREEXPERIMENT_REPORT.md` — registered protocol
- `results/v0.5/V0.5_RESUME_AUDIT.md` — crash/resume audit (execution history)
- Raw records: archived on Zenodo (DOI placeholder); hashes in
  `REPRODUCTION_MANIFEST.csv`
