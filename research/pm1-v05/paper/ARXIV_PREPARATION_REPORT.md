# arXiv Preparation Report — PM-1 V0.5

Date: 2026-08-19. Manuscript preparation only — no arXiv submission created.

---

## Artifact metadata added

- **Code and Data Availability section** added to the manuscript (§10.5):
  - GitHub: https://github.com/rikirinjani/pro-memoria (release v0.5.0)
  - Zenodo DOI: https://doi.org/10.5281/zenodo.22005884
  - States: 26,100 executed calls; H10–H250 executed; H500/H1000 registered
    but NOT executed; offline vs API-backed reproduction distinction; the
    116,100-call registered matrix was not executed.
- **Artifact citation** added as reference [10]:
  "R. Rinjani. *Pro Memoria (PM-1) V0.5 research artifact*, version 0.5.0.
  Zenodo. https://doi.org/10.5281/zenodo.22005884. (Research data/software
  release; not a peer-reviewed publication.)"
- **README** DOI placeholders replaced with the real Zenodo DOI and GitHub
  URL.

## Numerical consistency (frozen, verified)

- Completed: 26,100 | Registered: 116,100 | Unexecuted: 90,000
- Executed horizons: H10, H25, H50, H100, H250 — NOT executed: H500, H1000
- H250: P = 3,672,305; C = 38,366,105; 90.43% cumulative-token reduction
  relative to the accumulating conversational condition (never "compression")
- P reliability: 99.98% formatted responses; 100% state integrity; 100%
  digest continuity; 0 state divergence
- No scientific claims, methodology, or limitations changed. The baseline
  limitation (no summarization/compaction/retrieval/second-model comparison)
  remains stated.

## References / bibliography

- 9 verified references unchanged; artifact added as [10].
- No [CITATION NEEDED] placeholders remain in the manuscript. The former
  placeholder for formal agent-handoff taxonomies / stateful-agent surveys
  was rewritten as an explicit scope statement in Related Work.

## LaTeX / PDF readiness

- **No LaTeX pipeline exists in the repository** (no pdflatex/pandoc;
  the paper's PDF is produced by Typst from `PM1_PAPER_SUBMISSION.typ`).
  No `.tex` was fabricated.
- `PM1_PAPER_SUBMISSION.pdf` was regenerated offline from Typst with the new
  Code and Data Availability section (425 KB, A4, single-column).
- `PM1_PAPER_ARXIV_READY.md` is the arXiv-ready manuscript source.

## arXiv-specific issues / notes

1. **Source format:** arXiv prefers LaTeX; this manuscript is Markdown/Typst.
   Options before actual submission: (a) submit the PDF directly with
   arXiv's PDF-only option, (b) author a LaTeX version from
   `PM1_PAPER_ARXIV_READY.md`. Owner decision required.
2. **Author metadata:** name "Riki Rinjani" with affiliation Hisfarma IAI is
   in the manuscript/CITATION.cff; no ORCID provided — preserve the
   placeholder rather than inventing one.
3. **Title:** "Pro Memoria: Skip-Based State Transmission for Long-Horizon
   Agent Handoffs".
4. **Category suggestion:** cs.AI primary; cs.SE / cs.DC alternatives (owner
   choice at submission).
5. **Comments field (arXiv):** should note "26,100 completed API-backed
   handoffs; H500/H1000 registered but not executed; raw data on Zenodo
   (DOI 10.5281/zenodo.22005884)".
6. **Submission must be performed by the owner.** No arXiv account or
   submission was created.

## Remaining placeholders

- ORCID: placeholder (commented) in CITATION.cff — no invented value.
- Venue/publication status: none claimed; Zenodo record explicitly labeled a
  research data/software release, not peer-reviewed.

## Status

- **ARXIV PREPARATION STATUS = READY** (as Markdown/Typst + PDF; LaTeX
  conversion is an owner decision before submission)
