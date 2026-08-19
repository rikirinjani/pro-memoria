# PM1 Trading Benchmark — Simulator and Benchmark Protocol

**Status:** proposal pending review/approval  
**Scope:** architecture and minimum benchmark only; no simulator implementation

## 1. Canonical basis and constraints

The following were inspected before this proposal:

- `morse/context_assembly/state_layer.md`
- `morse/context_assembly/SPEC.md`
- `morse/context_assembly/assembler.py`
- `morse/context_assembly/writeback.py`
- `pm-adapter/README.md` and its default schema
- PM-Adapter QMS verification records

Canonical facts established by those artifacts:

1. Project state is stored under the configured PM-1 state directory
   (`<state_dir>/<project>`) in six PM-1 record files.
2. Records use a PM-1 JSON envelope with `seq`, `session_id`, `record_type`,
   `project`, and `payload`.
3. Context assembly is deterministic and priority ordered: task specification,
   relevant state, recent decisions, open-task worker reports, then history.
   The task specification is never silently trimmed.
4. PM-1 is transport; PM-Adapter is a separate deterministic schema adapter.
   The default agent-state schema is not a trading schema.
5. Phase 1 documents last-writer-wins/sequence checking, while the current
   `writeback.py` implementation appends based on the observed last sequence.
   The benchmark must measure this boundary rather than assume stronger
   concurrency guarantees.
6. The assembler tolerates malformed JSON lines by skipping them. This is an
   existing behavior and must be surfaced in robustness results, not hidden.

No canonical trading-specific schema, scenario, project decision, or
implementation exists. All recommendations below are unresolved until ratified.

## 2. Architecture proposal

Use a deterministic synthetic ledger simulator with four separated layers:

```text
Scenario manifest + seed
          |
          v
Hidden simulator truth ---- independent oracle/validator
          |
          +--> canonical PM-1 state projection
          |          |
          |          +--> context assembler --> worker packet
          |          +--> PM-Adapter --------> derived trading events
          |
          +--> deterministic event log and replay digest

worker packet --> fresh worker process --> structured action/report
                                      |
                                      v
                         validator --> ledger transition --> writeback
```

The benchmark owns scenario truth, logical time, event sequencing, replay
artifacts, fault injection, and independent validation. Existing PM-Adapter and
context-assembly components remain the owners of decoding and packet assembly;
the simulator must not reimplement those responsibilities.

### Separation rules

- The worker receives only the task specification, assembled packet, declared
  schema, and its fresh session identifier.
- Hidden truth, prior worker memory, the state directory, and the oracle are
  inaccessible to the worker.
- The oracle validates actions against hidden truth and is independent of the
  worker's report.
- P/L is an accounting invariant and outcome signal, not a strategy-quality or
  real-market claim.
- Optional semantic-memory enrichment is labeled enrichment and cannot replace
  canonical state, decisions, events, or artifacts.

## 3. State model

### 3.1 Hidden truth (never sent to workers)

```text
TruthState {
  run_id, scenario_version, seed,
  logical_tick,
  instrument,
  price_cents,
  cash_cents,
  position_qty,
  active_order,
  risk_gate,
  workflow_id,
  continuation_step,
  last_action_id
}
```

All monetary values are integer cents. No external market data or wall-clock
time participates in simulation identity.

### 3.2 Canonical projected state

`project_state.pm1` contains the latest state required for continuation:

```text
{
  workflow_id, continuation_id, logical_tick,
  instrument, price_cents, position_qty, cash_cents,
  active_order, risk_gate, last_action_id,
  tags: ["relevant", "trading"],
  pm1_frame, projection_digest
}
```

The worker must select the highest valid state sequence. Missing, stale, or
inconsistent required fields cause a fail-closed result; the worker must not
invent portfolio state.

The canonical state directory retains the six standard files:

| File | Benchmark use |
|---|---|
| `project_state.pm1` | current projected portfolio/workflow snapshot |
| `decisions.pm1` | ratified policy and decision revisions |
| `task_records.pm1` | per-step open/closed task lifecycle |
| `worker_reports.pm1` | action, evidence, and continuation report |
| `session_log.pm1` | audit-readable session chronology |
| `historical_trace.pm1` | compacted prior events/traces |

Decision revisions use stable `decision_id`, `supersedes`, and `effective_tick`
fields. A superseded decision remains in history; it is never overwritten or
silently deleted.

## 4. Event model

Every benchmark event is append-only and deterministically ordered:

```json
{
  "run_id": "run-...",
  "event_seq": 12,
  "logical_tick": 2,
  "event_type": "StateProjected",
  "workflow_id": "wf-...",
  "task_id": "step-2",
  "worker_session_id": "worker-2",
  "state_seq": 4,
  "payload": {}
}
```

Recommended event types:

`RunStarted`, `MarketTick`, `DecisionRecorded`, `DecisionSuperseded`,
`TaskDispatched`, `WorkerStarted`, `WorkerAction`, `OrderFilled`,
`StateProjected`, `ReportWritten`, `TaskClosed`, `FaultInjected`, and
`RunFinished`.

Event IDs, sequence numbers, ordering, scenario data, and action results are
derived from the seed and logical clock. Wall-clock timestamps may be retained
as diagnostics only and must not affect replay identity or digests.

## 5. Worker/session lifecycle

1. Create a run from scenario version, seed, model, registry hash, schema hash,
   and fault-plan hash.
2. Initialize hidden truth and the canonical PM-1 state fixture.
3. Assemble a packet using the existing context assembler.
4. Start a new worker process with no access to prior session memory or hidden
   files.
5. Require a structured result:

   ```json
   {
     "ok": true,
     "action": {"kind": "BUY", "quantity": 1},
     "observed_state_seq": 3,
     "report": {"evidence": [], "reason": "..."}
   }
   ```

6. Validate the action against hidden truth. Reject illegal, duplicated, or
   inconsistent actions without applying a ledger transition.
7. Apply the deterministic fill/ledger transition and project the next state.
8. Write the worker report and close that step's task record.
9. Destroy the worker. The next step receives a new worker and a newly
   assembled packet only.
10. Finish by comparing final truth, projected state, event log, decisions,
    reports, and expected digest.

`MISSING_REQUIRED_STATE`, `INVALID_ACTION`, `INVALID_CONFIG`, `STATE_CORRUPT`,
and `INCONCLUSIVE` are distinct outcomes. A fault-detection success is not an
ordinary control-run success.

## 6. Minimum viable benchmark protocol

### Control scenario

Use one synthetic instrument, immediate fills, no fees, no shorting, and a
three-step logical timeline:

```text
Initial: cash=100000 cents, position=0, price=10000 cents, risk_gate=OK
Tick 1:  entry condition holds; worker must BUY 1 at 10000 cents
Tick 2:  price=10100 cents; worker must SELL 1
Tick 3:  position is flat; worker must HOLD
Expected final: cash=100100 cents, position=0, active_order=none
```

The task specification defines the policy and allowed actions but intentionally
does not include current position or cash. Those facts must be recovered from
the PM-1 packet. The control protocol runs three fresh workers, one per tick.

### Required protocol cases

| Case | Expected classification |
|---|---|
| Control, three fresh workers | `PASS`; final truth digest matches |
| Same seed repeated three times | byte/digest-identical canonical outputs |
| Current state snapshot dropped | continuation failure, not guessed success |
| Latest JSON line truncated/corrupt | integrity or continuation failure is surfaced |
| Duplicate report/event | duplicate detected; no double fill |
| Reordered/stale sequence | rejection or explicit unsupported capability |
| Unknown model registry entry | `INVALID_CONFIG`, never a pass |
| Oversized task specification | assembler loud failure |
| Crash before writeback | `INCONCLUSIVE` until recovery semantics are ratified |

The benchmark is not valid if a negative case is counted as a successful
trading run merely because the worker guessed the expected action.

## 7. Evaluation metrics

### Primary

- **Fresh-continuation accuracy:** correct actions divided by eligible
  continuation steps.
- **Run correctness:** final hidden-truth digest equals the scenario oracle.
- **State fidelity:** required projected fields equal hidden truth at each
  checkpoint.
- **Packet fit:** task is present and `total_tokens <= packet_budget`.
- **Replay determinism:** repeated runs have identical canonical packet/event
  digests.
- **Writeback integrity:** expected unique records and valid sequence behavior.
- **Fault detection rate:** injected faults rejected or surfaced with the
  expected classification.

### Secondary and diagnostic

Packet size and section composition, synthetic raw-history compression ratio,
assembly latency, registry confidence/fallback use, decision supersession
visibility, P/L consistency, and event-log completeness.

No metric should be described as live-market alpha, investment performance, or
brokerage reliability.

## 8. Fault-injection strategy

Fault plans are explicit, seeded, versioned, and recorded as `FaultInjected`
events. Initial fault classes:

- drop latest projected state;
- corrupt or truncate a state record;
- inject stale or duplicate sequence/write;
- duplicate a report or fill event;
- reorder append-only records;
- remove or alter a decision revision;
- use an unknown model or schema hash;
- exceed packet/task budget;
- crash between action validation and writeback.

Each fault has an expected detection/classification and a run digest. The
simulator must report whether the fault was detected, not silently repair it.

## 9. Minimal implementation plan after approval

1. Ratify the scenario manifest, trading schema, action/report contract, status
   taxonomy, and registry fixture.
2. Implement the logical-clock simulator, integer-cent ledger, hidden oracle,
   event log, and replay digest.
3. Materialize PM-1 state and invoke the existing assembler and a dedicated
   trading PM-Adapter schema; do not fork their responsibilities.
4. Implement the fresh-worker subprocess runner and serialized input boundary.
5. Integrate writeback and test report/task sequence semantics explicitly.
6. Add the fault matrix, result report, and deterministic CI control gate.

## 10. Benchmark invalidation conditions

The benchmark result is invalid if any of the following occurs:

- worker can read hidden truth, prior transcripts, or the state directory;
- oracle derives expected outcomes from worker output;
- repeated identical inputs produce different canonical digests;
- wall-clock metadata changes replay identity;
- malformed/corrupt state is silently treated as valid without being reported;
- state, decision, event, or report provenance cannot be reconstructed;
- configuration errors are counted as continuation successes;
- real market data, brokerage APIs, or live execution enter the control path;
- the task specification includes the state the benchmark claims to test;
- a fault is declared detected without an observable validator result.

## 11. Unresolved decisions requiring approval

1. Exact trading schema fields and PM-1 frame encoding.
2. Whether fees, slippage, partial fills, and order expiry are deferred beyond
   the minimum protocol.
3. Required stale-write behavior: reject, classify unsupported, or add a
   benchmark-owned compare-and-swap wrapper.
4. Crash recovery semantics and whether crash cases are required in the first
   benchmark release.
5. Token validation policy: heuristic assembler count only or an additional
   pinned-tokenizer audit.
6. Whether state projection stores `price_cents` in addition to the minimum
   continuation fields.

Until these are ratified, this document is a proposal and the implementation
plan must not be expanded into simulator code.
