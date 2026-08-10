# PM-1 Status Recap

> Last updated: 2026-08-10

## What PM-1 is

A zero-dependency, token-efficient state telemetry protocol for agents. Agent state
(session, outcome, duration, files, failures) encodes to Morse-style symbols,
compressing JSON-equivalent telemetry ~7× (token savings ~86%). Two repos:

- **`rikirinjani/pro-memoria`** v1.0.0 — the protocol (core/dsp/lexicon/hybrid/protocol/handshake + opencode_plugin CLI, failsafe, dashboard)
- **`rikirinjani/pm-adapter`** v1.0.0 — the consumer (deterministic schema expansion: `to_english` / `to_json` / `to_semantic` / `to_events` + domain schemas)

## Real-world usage (trace corpus, Jul 14 → Aug 7 2026)

| Metric | Value |
|---|---|
| Traces recorded | 948 |
| Raw size | 121,345 chars PM-1 vs 890,182 B JSON |
| Compression ratio | 0.14× |
| Token savings | 86.4% |
| Pass rate | 94.5% (896 pass / 23 partial / 15 unknown / 14 fail) |
| Heaviest day | Jul 24 (104), Jul 31 (103) |

## Verified engineering claims (independently reviewed)

- **86.4% token savings** across 948 real traces
- **99.9% decode rate** on 698-trace live validation
- **67.1% human-calibrated mechanical ceiling** (coordination events, Amdahl-bound reasoning)
- ECC: single-bit errors silently corrected; only double-bit raises
- Wheel packaging fixed (bundles all modules + schemas, git-installable)

## Compliance state (2026-08-07 audit)

- 17/17 fail traces ↔ failure records matched, 0 unmatched
- 8 orphan failure records are expected non-gaps (failsafe auto-records, retrace entries, one partial)
- Both repos have `CONTRIBUTING.md`

## Known open items

- `pro-memoria` not on PyPI (git-only dependency) — only needed for public PyPI release
- Three follow-on systems not yet built: observation encoder, memory taxonomy, deployment lifecycle
