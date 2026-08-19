# PM-1 V0.5 — Release Record

- **Release version:** v0.5.0
- **Release date:** 2026-08-19
- **Git commit SHA:** 86b1f41 (release HEAD; artifact 0907e5a)
- **GitHub repository:** https://github.com/rikirinjani/pro-memoria
- **Artifact path in repo:** `research/pm1-v05/`
- **Zenodo DOI:** 10.5281/zenodo.22005884

## Experiment scope (frozen)

- Registered calls: **116,100**
- Completed calls: **26,100**
- Unexecuted (registered, not run): **90,000**
- Executed horizons: **H10, H25, H50, H100, H250**
- **H500 / H1000: NOT EXECUTED**
- Execution intentionally stopped after H250 (sufficient evidence for the
  scoped conclusion; deliberately bounded result)

## Principal result (H250)

- P cumulative tokens: **3,672,305**
- C cumulative tokens: **38,366,105**
- **90.43% cumulative-token reduction relative to the accumulating
  conversational condition** (a difference between two handoff strategies,
  not a compression ratio)
- P reliability: **99.98% successfully formatted worker responses; 100% state
  integrity; 100% digest continuity; 3 PARSE_ERROR; 0 state divergence**
- V0.5 overall: 5 non-PASS records (3 PARSE_ERROR, 1 ACTION_ERROR,
  1 STATE_CORRUPTION); the two state-related failures occurred in C at H100

## Data archive (Zenodo, pending)

| Artifact | SHA-256 |
|---|---|
| v05a_full_checkpoint.json | e69864d610305b349d2bb95a0484e0b4907fbe0fb6ad93931c97cc3871238e0e |
| v05a_full_hop_records.json | ee8547648dc73e4e6a5444a0aed2e768bf4029200aa05514cfd078d50fbc89b7 |
| v04a_full_hop_records.json | a56c3cba5ebbfb7ae1788c235e6d8206eb8965ad412b5c7f6ef639abc4c5e27c |

Full manifest: `paper/REPRODUCTION_MANIFEST.csv`.

## Reproducibility

- Offline tests: **243 passed** (artifact-preservation tests that assert the
  private working-repo layout were excluded from the public release; the
  remaining suite is the benchmark's functional offline suite)
- Offline summary regeneration: `benchmark/regenerate_summary.py` reproduces
  the published summary exactly from raw hop records (26,100 calls; horizons;
  failure counts) — verified against the published consolidation
- API-backed reproduction requires provider credentials and is not free; it
  does not require running H500/H1000

## Pre-release checks

- Secret scan (staging/integrated tree): **0 confirmed secrets**
- Machine-specific paths: **0** (one provenance reference to the internal
  `self-harness/traces/` harness remains in a historical pilot report; it is
  not a machine path)
- Git history audit: secret file never committed or pushed; no Git repo
  existed in the benchmark working directory; old credential rotated by owner

## License / citation

- Code: MIT (see LICENSE); Data: CC BY 4.0; see CITATION.cff
- Placeholders remain for Zenodo DOI (insert after deposition)
