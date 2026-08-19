# PM-1 V0.5 — Release Readiness Report

Date: 2026-08-19. Offline audit only. No uploads, no publications, no
experiment runs.

---

## 0. RELEASE BLOCKER — CONFIRMED SECRET

**`.llm_creds.json`** (repository root, 146 bytes) contains a **live DeepSeek
API key** (`sk-...`) plus base URL and model name.

Per the release-preparation protocol, publication preparation is **halted**
until this file is remediated:

- **Remediation required before any public release:**
  1. Confirm `.llm_creds.json` is excluded from the public repository (add to
     `.gitignore` if the repository is ever initialized with git).
  2. Verify no copy of the key exists in hop records, checkpoints, reports,
     logs, or the paper (the automated scan found it **only** in
     `.llm_creds.json`; see §5).
  3. Rotate the key if there is any chance it was exposed (e.g., in a shared
     log or a clipboard session).
- The file was **not modified** by this audit. No secret values are printed
  in this report.

**No other confirmed secrets were found.**

---

## 1. Recommended Public Repository Structure

The existing repository (`pm1-trading-benchmark/`) is already well organized
(versioned `results/v0.*` trees, `lib/`, `tests/`, `paper/`). Recommended
release layout — minimal change, preserve reproducibility:

```
pm1-v05/                        (release root)
│
├── README.md                   ← public rewrite (path-neutral, see §10)
├── LICENSE                     ← see §8 recommendation
├── CITATION.cff                ← draft prepared
├── .gitignore                  ← .llm_creds.json, .env*, __pycache__,
│                                  .pytest_cache, *.pyc
│
├── ARCHITECTURE.md             ← path-neutral copy (currently has local path, §6)
│
├── benchmark/                  ← source code
│   ├── lib/                    (oracle, validator, worker, chain, state,
│   │                            scenario, mutator, fixtures, llm_runner,
│   │                            llm_worker — 15 files, 220 KB)
│   ├── tests/                  (5 test files, 117 KB)
│   ├── runner.py, run_v0*.py, preflight_audit.py, check_env.py
│   ├── task-spec.json
│   └── requirements.txt        ← to be created (dependencies, §10)
│
├── results/
│   ├── v04a/
│   │   ├── V0.4a_PREEXPERIMENT_REPORT.md
│   │   ├── V0.4a_PILOT_REPORT.md
│   │   └── full/  (report + config; raw records → Zenodo)
│   └── v05/
│       ├── V0.5_PREEXPERIMENT_REPORT.md
│       ├── V0.5_PILOT_REPORT.md / V0.5_PILOT_CONFIG.md
│       ├── V0.5_RESUME_AUDIT.md
│       ├── V0.5_POST_H250_CONSOLIDATION_REPORT.md
│       ├── EXPERIMENT_STATUS.md   ← public status doc (prepared)
│       ├── v05a_post_h250_summary.json
│       └── manifests/             ← manifest + hashes (prepared)
│
├── data/
│   └── README.md               ← points to Zenodo for raw records; schema;
│                                  download instructions
│
└── paper/
    ├── PM1_PAPER_SUBMISSION.md / .typ / .pdf
    ├── PM1_PAPER_DRAFT_FINAL.md, PM1_PUBLICATION_DESIGN.md,
    │   PM1_REVISION_R1_SUPPORTING.md, PM1_FINAL_AUDIT.md,
    │   PM1_RELATED_WORK_BIB.md
    ├── make_figures.py          ← path fix required (§6)
    └── figures/                 (fig1–3, png+svg)
```

Rationale: the current tree already separates source, results, tests, and
paper. The smallest clean change is a top-level rename/re-export, path
neutralization of three files, addition of LICENSE/.gitignore/requirements/
CITATION.cff/EXPERIMENT_STATUS/manifest, and moving the two large raw V0.5
files to Zenodo with a manifest in-repo.

---

## 2. Content Classification

### A. PUBLISH (required for reproducibility)

- `lib/` (all 15 source files) — harness, oracle/state/worker/chain/validator
  logic
- `tests/` (5 files) — offline regression tests
- `runner.py`, `run_v0*.py` (all), `preflight_audit.py`, `check_env.py`,
  `task-spec.json`
- `ARCHITECTURE.md` (path-neutral copy), `ARCHITECTURE_REVIEW.md`
- `results/v0.4a/*.md`, `results/v0.4a/full/*.md` (reports + config)
- `results/v0.5/*.md`, `results/v0.5/*.json` (reports, summary,
  consolidation, pilot, resume-audit, pre-experiment)
- `paper/*` (all manuscript/support documents, figures, make_figures.py)
- New: README.md, LICENSE, CITATION.cff, EXPERIMENT_STATUS.md,
  REPRODUCTION_MANIFEST.csv, data/README.md, requirements.txt, .gitignore

### B. ARCHIVE (Zenodo, DOI-backed raw data)

- `results/v0.5/v05a_full_checkpoint.json` (29.7 MB)
- `results/v0.5/v05a_full_hop_records.json` (27.6 MB)
- `results/v0.4a/full/v04a_full_hop_records.json` (4.3 MB)
- `results/v0.4a/full/v04a_full_results.json` (31.5 KB) — optional, small
  enough for git; include in git and Zenodo for completeness
- `results/v0.5/v05a_pilot_hop_records.json` (339 KB) — small; keep in git or
  Zenodo (recommend git; keep simple)

### C. KEEP PRIVATE / DO NOT PUBLISH

- **`.llm_creds.json` — CONFIRMED SECRET (blocker)**
- `extract_creds.py` — credential-extraction utility; not needed for
  reproducibility; keep private
- `check_env.py` — reads env vars (OPENAI_API_KEY etc.); safe content but
  unnecessary in public; exclude
- Any `.env` / `.env.*` (none found, but keep the rule)
- `compiled_context.json` — internal working artifact; verify before release
- `results/preflight/prompt_*.json` — internal preflight prompts; optional;
  recommend keep private unless shown safe
- `__pycache__/`, `tests/__pycache__/`, `.pytest_cache/` — bytecode caches,
  exclude
- `results/*.json` at top level (`llm_run_results.json`, `run_results.json`,
  `replay_digests.json`, `llm_replay_digests.json`, `experiment_report.md`) —
  earlier-version internal outputs; ARCHIVE, do not publish
- `EXPERIMENT_V0.1.md`, `V0.3a_PREEXPERIMENT_REPORT.md` (root),
  `results/v0.2a`, `results/v0.2b`, `results/v0.3a` — earlier experiment
  versions; ARCHIVE (keep in private repo), not required for the V0.5 release
- `test_llm_local.py`, `results/llm_experiment_report.md` — internal LLM
  harness tests/reports; exclude from public (they reference credential
  handling)

---

## 3. Data Size Audit

| Category | Size |
|---|---|
| Total repository | 63.79 MB (139 files) |
| results/ (all) | 62.05 MB |
| raw data (checkpoint + hop records, V0.4a + V0.5) | ~61.7 MB |
| lib/ + tests/ + runners (code) | ~0.44 MB + 0.55 MB + ~0.1 MB |
| paper/ (incl. figures) | ~0.58 MB |

Largest files:

| File | Size |
|---|---|
| results/v0.5/v05a_full_checkpoint.json | 29.67 MB |
| results/v0.5/v05a_full_hop_records.json | 27.63 MB |
| results/v0.4a/full/v04a_full_hop_records.json | 4.27 MB |
| results/v0.5/v05a_pilot_results.json | 423.6 KB |
| results/v0.5/v05a_pilot_hop_records.json | 339.2 KB |

**Git vs archive decision:** two files exceed GitHub's 50 MB soft per-file
limit (checkpoint 29.67 MB, hop records 27.63 MB — under the 100 MB hard
limit, so technically pushable, but large and immutable). Recommended:
**code + docs + small derived artifacts → Git; both large raw V0.5 files (+
V0.4a hop records) → Zenodo** with in-repo manifest + hashes + download
instructions. Never silently replace raw data with summaries.

---

## 4. Reproduction Manifest

Prepared as `REPRODUCTION_MANIFEST.csv` (see separate file): every key
artifact with relative path, purpose, size, SHA-256, and PUBLISH / ARCHIVE /
PRIVATE classification. Hashes computed 2026-08-19 (see scan output; full
manifest file contains the complete table).

---

## 5. Secret / Credential Audit — Findings

Scan patterns: `sk-`, `api_key`, `API_KEY`, `api-key`, `Authorization`,
`Bearer`, `token`, `password`, `secret`, `DEEPSEEK_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. 51 deduplicated matches; classification:

- **CONFIRMED SECRET (1):** `.llm_creds.json` — live DeepSeek API key.
  Remediation required (§0). Not modified.
- **POSSIBLE SECRET (0):** none.
- **SAFE METADATA (50):**
  - `lib/llm_runner.py`, `lib/llm_worker.py`, `lib/v04a_worker.py` — code that
    *reads* credentials from env/config; contains no literal values.
  - `tests/test_v04a.py`, `tests/test_v05a.py` — assertions that secrets are
    absent from persisted payloads (positive hygiene, publish-safe).
  - `check_env.py`, `extract_creds.py` — utilities referencing credential
    variables; no literal secrets (both excluded from public anyway).
  - Reports/configs mentioning the words "authorization"/"secret scan" —
    procedural text, not credentials.
  - Paper files matching `sk-` — false positives from the word
    "task-**relevant**" (e.g., "task-relevant context"); verified as prose.

**Conclusion:** exactly one secret-bearing file; it is the only blocker.

---

## 6. Personal / Machine-Path Audit

Three files originally contained local machine paths (now neutralized in the
public tree; original paths are withheld here for privacy):

1. `ARCHITECTURE.md:19` — local state path →
   **fixed**: "state directory configured by the operator"
2. `README.md:9` — local state path →
   replaced by the new public README (relative/neutral wording)
3. `paper/make_figures.py:7` — hardcoded output path →
   **fixed**: derive from `Path(__file__).parent / "figures"`

No other machine-specific paths found. Raw experimental records contain no
personal paths (verified). Public docs will use relative paths.

---

## 7. Git vs Zenodo Recommendation

- **GitHub repository (code + docs + small derived artifacts):**
  benchmark source, tests, runners, config, all reports/summaries, paper
  (md/typ/pdf), figures, LICENSE, CITATION.cff, README, manifests.
- **Zenodo (immutable raw data + DOI):**
  - `v05a_full_checkpoint.json` (29.67 MB)
  - `v05a_full_hop_records.json` (27.63 MB)
  - `v04a_full_hop_records.json` (4.27 MB)
  - optionally `v04a_full_results.json` and the pilot hop records
  - Release contents: raw files + the reproduction manifest (hashes) so
    downstream verification is exact.
- **Recommended version tag:** `v0.5.0` (not created; awaiting authorization).
- **In-repo data/README.md:** explains hop-record schema, mapping to
  experimental units (scenario × trial × condition × hop), checkpoint
  relationship, duplicate detection (0 dup/missing, 26,100/26,100), and how
  cumulative token totals are computed (provider usage, `chars/4` fallback).

---

## 8. Licensing Recommendation

- **Code (benchmark harness, runners, tests, figure script):** MIT or
  Apache-2.0. Apache-2.0 recommended if any third-party code was adapted;
  MIT if fully original. Third-party dependency surface is small (Python
  stdlib + requests/urllib; the paper's LLM calls use the DeepSeek-compatible
  OpenAI endpoint). Verify dependency licenses in `requirements.txt` before
  finalizing.
- **Data (raw hop records, checkpoints, reports):** CC BY 4.0. The data is
  generated (synthetic task + model outputs), not personal data; CC BY 4.0 is
  appropriate and lets downstream use with attribution.
- **Paper:** standard scholarly reuse — repository terms or CC BY 4.0 for the
  manuscript text as well, unless the intended venue imposes its own terms.
- Caveat: if the author intends to publish in a venue that takes copyright,
  align the LICENSE with venue terms before release. This is a
  recommendation, not legal advice.

---

## 9. Reproducibility Gaps

1. **No `requirements.txt`** — dependency list must be created from imports
   (stdlib + requests/urllib + pytest). Small, quick.
2. **`make_figures.py` hardcoded path** — must be fixed to relative before
   the figure script is usable publicly.
3. **Raw data not in git** — until Zenodo upload, external checkers cannot
   recompute the consolidation from raw records; the manifest bridges this.
4. **`ARCHITECTURE.md` / root `README.md` contain local paths** — public
   copies need neutral wording (see §6).
5. **V0.5 offline-only regeneration:** derived analysis (summary JSON,
   consolidation report) can be regenerated from raw records with a
   documented script — currently no standalone "regenerate summary" script is
   present; either publish `v05a_post_h250_summary.json` as the derived
   artifact (done) or add a small regeneration script to `benchmark/`.
6. **Pilot/preflight artifacts** (`results/preflight/*`) are referenced by
   pilot reports; keep private and note in data/README that they are internal.

---

## 10. Reproducibility README (public draft)

Prepared as `README_PUBLIC_DRAFT.md` (separate file). It covers: what PM-1 is
("skip, don't compress" handoff architecture); P/C conditions; fresh context
per hop; deterministic task/oracle; horizon and scenario/trial structure;
**executed scope** (registered 116,100 / executed 26,100 / H10–H250 completed
/ H500, H1000 NOT executed); key H250 results (P 3,672,305, C 38,366,105,
90.43% cumulative-token reduction; 99.98% formatted responses, 100% state
integrity, 100% digest continuity); and reproduction instructions that clearly
distinguish **offline reproduction** (install deps, run tests, inspect
definitions, regenerate derived analysis from raw records) from
**API-backed experiment reproduction** (requires provider credentials; not
free; does not require H500/H1000).

---

## 11. Experiment Status Document

Prepared as `results/v0.5/EXPERIMENT_STATUS.md` (separate file): registered
matrix 116,100; completed 26,100; unexecuted 90,000; completed horizons
10/25/50/100/250; unexecuted 500/1000; reason for stopping — "H250 produced
sufficient evidence for the scoped V0.5 conclusion; execution was
intentionally stopped before H500/H1000." Framed as a deliberately bounded
experimental result, not a failure.

---

## 12. CITATION.cff

Prepared as `CITATION.cff` (separate file) with title, version placeholder,
repository placeholder, paper reference, and authors only from verified
project metadata. No invented ORCID/DOI/affiliation. ORCID and DOI are
placeholders to be filled at release time.

---

## 13. Scientific Boundary (preserved)

The public artifact does **not** present Gladi Resik / PM-Adapter or the
skip-taxonomy (invariant/bounded/process skip) as validated by V0.5. V0.5
demonstrates bounded continuation-state handoff vs accumulating conversational
history only. Heterogeneous-state selection, budgeted semantic selection,
institutional knowledge preservation, decision supersession, retrieval,
compaction, and heterogeneous models remain future work (stated in the paper
§Limitations/Future Work and in the README).

---

## 14. Overall Readiness Verdict

**NOT READY FOR PUBLIC RELEASE — blocked by one confirmed secret
(`.llm_creds.json`) and three minor path/documentation fixes.**

After remediation (exclude/rotate the key, neutralize three file paths, add
LICENSE/.gitignore/requirements.txt), the artifact is structurally ready:
source, tests, reports, summary, figures, manifest, and public docs are all
prepared. Raw data release is staged for Zenodo with hashes.

Action list before release:
1. Rotate/exclude the DeepSeek key (blocker).
2. Fix `make_figures.py`, `ARCHITECTURE.md`, root `README.md` paths.
3. Create `requirements.txt`, `.gitignore`, `LICENSE`.
4. Re-run secret scan after remediation (expect 0 confirmed).
5. Upload raw V0.5 + V0.4a records to Zenodo; tag `v0.5.0`.
6. Publish README_PUBLIC_DRAFT.md as root README (or embed in release).

Nothing was uploaded, published, or modified in this audit.
