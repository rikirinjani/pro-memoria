# Data — raw experimental records

## What lives here

This directory is the pointer for the large raw experimental artifacts. They
are archived on **Zenodo** (DOI: *placeholder — to be assigned at release*),
not in this Git repository, because they are large, immutable experiment
outputs:

| Artifact | Size (approx.) | SHA-256 (see REPRODUCTION_MANIFEST.csv) |
|---|---|---|
| `results/v0.5/v05a_full_checkpoint.json` | 29.7 MB | in manifest |
| `results/v0.5/v05a_full_hop_records.json` | 27.6 MB | in manifest |
| `results/v0.4a/full/v04a_full_hop_records.json` | 4.3 MB | in manifest |

## Download

Replace the `data/` placeholders with the Zenodo record contents at release
time. The reproduction manifest (`paper/REPRODUCTION_MANIFEST.csv`) lists every
artifact with its SHA-256 hash; verify downloaded files against it.

## Hop-record schema

Each hop record (one per completed API call; 26,100 total for V0.5) contains:

- identity: `horizon`, `scenario_id`, `chain_id`, `hop_index`, `condition`
- state: `received_state`, `expected_state`, `actual_state`
- actions: `worker_action`, `expected_action`, `worker_quantity`
- integrity: `divergence`, `state_digest_expected`, `state_digest_actual`
- tokens: `input_tokens`, `output_tokens`, `cumulative_*`, `usage_available`
- context: `transmitted_context_tokens`, `transmitted_context_chars`,
  `pm1_packet_size`, `history_size`
- classification: `classification` (PASS / PARSE_ERROR / ACTION_ERROR /
  STATE_CORRUPTION)

## Mapping to experimental units

- 10 scenarios × 3 trials × 2 conditions at each executed horizon
  (H10: 600, H25: 1,500, H50: 3,000, H100: 6,000, H250: 15,000 calls).
- Trials are reconstructed by `chain_id`; `scenario_id` identifies the
  scenario; `condition` is P or C.
- Duplicate detection: call IDs are unique per hop; the audit found 0
  duplicates and 0 missing records (26,100/26,100 persisted).
- Checkpoint relationship: `v05a_full_checkpoint.json` mirrors the hop records
  and matched them exactly in the post-run audit.

## Cumulative token totals

Cumulative totals are the sum of per-hop provider-reported `input_tokens` +
`output_tokens` (falling back to the documented `chars/4` estimate only when
provider usage is absent). Regenerate offline with:

```
python benchmark/regenerate_summary.py --records <records.json> --out out.json
```

The regenerated values matched the published summary exactly in verification.
