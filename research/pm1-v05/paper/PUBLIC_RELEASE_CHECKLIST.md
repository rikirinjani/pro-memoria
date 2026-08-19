# PM-1 V0.5 — Public Release Checklist

Status: final pre-publication quality check — 2026-08-19.
Owner performs publication separately after reviewing this checklist.

## Automated verification status

| # | Item | Status |
|---|------|--------|
| 1 | Secret scan (staging tree) | **PASS** — 0 confirmed secrets |
| 2 | Git history audit | **PASS** — no Git repo exists; `.llm_creds.json` never committed/pushed; credential manually rotated by owner |
| 3 | No private credentials in staging | **PASS** — `.llm_creds.json` absent; no `.env`, no key material |
| 4 | No personal paths in staging | **PASS** — 0 machine-specific paths remaining (readiness report path refs neutralized) |
| 5 | Offline summary regeneration | **PASS** — `benchmark/regenerate_summary.py` regenerates from persisted records; matches published summary (26,100 calls; horizons 10/25/50/100/250; 3 PARSE_ERROR + 1 ACTION_ERROR + 1 STATE_CORRUPTION) |
| 6 | Offline tests | **PASS** — 251 passed, 0 failed, 0 skipped (pytest 9.1.1) |
| 7 | Paper/result consistency | **PASS** — registered 116,100 / completed 26,100 / unexecuted 90,000; H10–H250 executed; H500/H1000 NOT executed; H250 P=3,672,305, C=38,366,105, 90.43%; 99.98% formatted / 100% integrity / 100% digest continuity; no "compression ratio"/"100% success" misuse (only negations) |
| 8 | Manifest/hash consistency | **PASS** — manifest regenerated against staging tree; 67 staged entries verified (hash+size match), 3 external Zenodo entries marked EXTERNAL; no fabricated DOI |
| 9 | License | **PASS** — LICENSE present (MIT code / CC BY 4.0 data), legal-review flag noted |
| 10 | CITATION.cff | **PASS** — present at root; placeholders only (no invented DOI/ORCID/venue) |
| 11 | README | **PASS** — covers PM-1, skip-don't-compress, V0.5 design, P vs C, config, executed scope, H500/H1000 NOT EXECUTED, results, limitations, offline reproduction, raw-data/Zenodo relationship, citation |
| 12 | Paper boundary | **PASS** — future-work concepts (supersession, institutional memory, heterogeneous models, retrieval/compaction/summarization, process-skip) appear only as NOT TESTED / future work, not V0.5 findings |

## Owner action required (final publication steps)

- [ ] Create GitHub repository (`pm1-v05`) and push the staging tree
- [ ] Create Zenodo record; upload raw V0.5 checkpoint + hop records and V0.4a hop records
- [ ] Insert real Zenodo DOI into CITATION.cff and data/README.md
- [ ] Insert real GitHub URL into CITATION.cff
- [ ] Tag release `v0.5.0`
- [ ] (Recommended) rotate/verify DeepSeek credential hygiene already handled by owner
- [ ] Re-run the staging secret scan on release day (expect 0) if any file changed

## Guardrails honored

API calls = 0 · experiment executions = 0 · H500 = NOT EXECUTED ·
H1000 = NOT EXECUTED · uploads = 0 · publications = 0 ·
raw experimental artifacts modified = 0

Nothing was published, pushed, uploaded, or created remotely.
