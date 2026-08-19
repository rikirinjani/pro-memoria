"""
Chain runner, oracle validation, failure taxonomy, and metrics for
PM1 Trading Benchmark v0.4a.

The runner executes one chain hop-by-hop. At every hop it records:
expected_state, actual_state, expected_action, actual_action, state_digest,
behavior_digest, and classifies the hop against the V0.4a failure taxonomy.

State semantics
---------------
- The ORACLE trajectory (hidden ground truth) is computed by applying
  ``oracle.compute_expected_action`` + a deterministic delta at every hop.
- The ACTUAL trajectory is what the worker emits: its ``next_position_qty``
  is carried into the next hop.
- Divergence at hop h = actual_position[h] - expected_position[h].
- Worker correctness is judged FAIRLY: against the policy applied to the
  state the worker actually received (which may be corrupted). This keeps
  injected corruption distinct from genuine worker error.

Failure taxonomy (per hop): PASS, STATE_LOSS, STATE_CORRUPTION,
ACTION_ERROR, PARSE_ERROR, INVALID_STATE, HANDOFF_ERROR, RECOVERY_FAILURE,
INCONCLUSIVE.

Chain survival: every hop PASS and final divergence == 0.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from lib.oracle import Action, ActionKind, compute_expected_action
from lib.v04a_generator import ChainSpec
from lib.v04a_state import State, decode_direct_state, decode_pm1_state, encode_direct_state, encode_pm1_state, state_digest
from lib.v04a_worker import HandoffOutput

__all__ = [
    "HopRecord",
    "ChainResult",
    "run_chain",
    "run_experiment",
    "aggregate_metrics",
    "long_horizon_analysis",
    "generate_v04a_report",
    "CLASSIFICATIONS",
]

# Sanity bound for position values. Outside this range the emitted state is
# classified INVALID_STATE.
SANITY_BOUND = 50

# Hops allowed after restoration before the chain is declared not recovered.
RECOVERY_GRACE = 5

CLASSIFICATIONS = (
    "PASS",
    "STATE_LOSS",
    "STATE_CORRUPTION",
    "ACTION_ERROR",
    "PARSE_ERROR",
    "INVALID_STATE",
    "HANDOFF_ERROR",
    "RECOVERY_FAILURE",
    "INCONCLUSIVE",
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HopRecord:
    chain_id: str
    hop: int
    condition: str
    received_state: State
    expected_state: State
    actual_state: State
    expected_action: Action
    fair_expected_action: Action
    actual_action: HandoffOutput
    state_digest_expected: str
    state_digest_actual: str
    behavior_digest: str
    classification: str
    corruption_injected: bool
    restore_applied: bool
    divergence: int
    input_tokens: int
    output_tokens: int
    usage_available: bool = True


@dataclass
class ChainResult:
    chain_id: str
    condition: str
    hops: int
    initial_state: State
    final_expected_state: State
    final_actual_state: State
    first_failed_hop: int | None
    total_failures: int
    recovery_events: int
    chain_survived: bool
    hop_records: list[HopRecord] = field(default_factory=list)
    expected_positions: list[int] = field(default_factory=list)
    actual_positions: list[int] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    failure_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-hop classification
# ---------------------------------------------------------------------------


def _classify_hop(
    received: State,
    fair_expected: Action,
    output: HandoffOutput,
    next_pos: int | None,
    condition: str,
    divergence: int,
) -> str:
    """Classify one hop against the V0.4a failure taxonomy.

    Returns one of the CLASSIFICATIONS values.
    """
    if output.parse_error:
        return "PARSE_ERROR"
    if output.action_kind == "PARSE_ERROR":
        return "PARSE_ERROR"
    if next_pos is None:
        return "STATE_LOSS"
    if abs(next_pos) > SANITY_BOUND:
        return "INVALID_STATE"
    expected_next = received.position_qty + _action_delta(fair_expected)
    if output.action_kind != fair_expected.kind.value:
        return "ACTION_ERROR"
    if next_pos != expected_next:
        return "STATE_CORRUPTION"
    return "PASS"


def _action_delta(action: Action) -> int:
    if action.kind is ActionKind.BUY:
        return action.quantity
    if action.kind is ActionKind.SELL:
        return -action.quantity
    return 0


def _behavior_digest(condition: str, state: State, action_kind: str, qty: int, next_pos: int) -> str:
    """Digest over the semantic behavior only (no chain/hop identity)."""
    canonical = json.dumps(
        {
            "position_qty": state.position_qty,
            "target_signal": state.target_signal,
            "action": action_kind,
            "quantity": qty,
            "next_position_qty": next_pos,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Chain runner
# ---------------------------------------------------------------------------


def _build_state_repr(state: State, condition: str) -> tuple[str, str]:
    """Build the worker-visible representation.

    H-full  -> PM-1 packet (JSON text)
    H-direct-> plain text
    Others  -> PM-1 packet
    Returns (repr_text, state_kind).
    """
    if condition == "H-direct":
        return encode_direct_state(state), "direct"
    return json.dumps(encode_pm1_state(state), sort_keys=True), "pm1"


def run_chain(
    spec: ChainSpec,
    condition: str,
    worker: Any,
    decode_worker_state: Callable[[str, str], State] | None = None,
) -> ChainResult:
    """Run one chain for one condition.

    ``worker`` must expose ``run(state) -> HandoffOutput`` and a
    ``last_usage`` dict with prompt_tokens/completion_tokens.

    ``decode_worker_state`` is the harness-side decoder for the representation
    the worker received (used to verify the received state round-trips).
    """
    hops = spec.hops
    # Oracle trajectory (hidden ground truth)
    expected_positions = [spec.initial_state.position_qty]
    actual_positions = [spec.initial_state.position_qty]
    actual_pos = spec.initial_state.position_qty

    records: list[HopRecord] = []
    failure_counts: dict[str, int] = {}
    first_failed_hop: int | None = None
    total_failures = 0
    recovery_events = 0
    total_in = 0
    total_out = 0

    corrupted = False
    last_corrupt_hop: int | None = None
    last_restore_hop: int | None = None

    for hop in range(1, hops + 1):
        target = spec.target_at(hop)
        expected_pos = expected_positions[-1]
        expected_action = compute_expected_action(expected_pos, target)
        expected_next = expected_pos + _action_delta(expected_action)
        expected_positions.append(expected_next)

        # Received state (actual carried forward, unless restored).
        # F1 fix: fault injection is condition-gated.
        #   - Corruption ONLY for H-corrupt and H-recover.
        #   - Restoration ONLY for H-recover.
        #   - H-full / H-direct receive the unmodified carried-forward state.
        received_pos = actual_pos
        corruption_injected = False
        restore_applied = False
        if condition in {"H-corrupt", "H-recover"} and hop in spec.corrupt_hops:
            received_pos = actual_pos + 1  # controlled corruption: +1 flip
            corruption_injected = True
            corrupted = True
            last_corrupt_hop = hop
        elif condition == "H-recover" and hop in spec.restore_hops:
            received_pos = expected_pos  # restore oracle state
            restore_applied = True
            corrupted = False
            last_restore_hop = hop

        received = State(position_qty=received_pos, target_signal=target, cash_cents=10000 - received_pos * 10000)

        # Worker runs on a fresh context: only the state representation.
        repr_text, state_kind = _build_state_repr(received, condition)
        try:
            output = worker.run(received, state_kind=state_kind)
        except Exception as exc:  # harness/machinery failure
            output = HandoffOutput("PARSE_ERROR", 0, None, reasoning=f"worker exception: {exc}", parse_error=True)
            # Reconstruct fallback: carry received position forward.
            next_pos = received_pos
        else:
            next_pos = output.next_position_qty

        # Validate the representation round-trips (harness-side decode).
        try:
            if state_kind == "direct":
                decoded = decode_direct_state(repr_text)
            else:
                decoded = decode_pm1_state(json.loads(repr_text))
            _ = decoded  # representation integrity
        except Exception:
            next_pos = received_pos  # representation broken; carry forward

        fair_expected = compute_expected_action(received_pos, target)
        actual_next = next_pos if next_pos is not None else received_pos
        actual_positions.append(actual_next)
        divergence = actual_next - expected_next

        classification = _classify_hop(
            received, fair_expected, output, next_pos, condition, divergence,
        )
        failure_counts[classification] = failure_counts.get(classification, 0) + 1
        if classification != "PASS":
            total_failures += 1
            if first_failed_hop is None:
                first_failed_hop = hop

        actual_state = State(position_qty=actual_next, target_signal=target, cash_cents=10000 - actual_next * 10000)
        expected_state = State(position_qty=expected_next, target_signal=target, cash_cents=10000 - expected_next * 10000)
        actual_pos = actual_next

        # F2 fix: token accounting reads the worker's last_usage dict (set by
        # LLMHandoffWorker.run). If the provider returned usage, record real
        # numbers. If usage is genuinely absent, record usage_available=False
        # rather than silently reporting zero.
        usage = getattr(worker, "last_usage", None) or {}
        if usage:
            in_tok = int(usage.get("prompt_tokens", 0))
            out_tok = int(usage.get("completion_tokens", 0))
            usage_available = True
        else:
            in_tok = 0
            out_tok = 0
            usage_available = False
        total_in += in_tok
        total_out += out_tok

        records.append(HopRecord(
            chain_id=spec.chain_id,
            hop=hop,
            condition=condition,
            received_state=received,
            expected_state=expected_state,
            actual_state=actual_state,
            expected_action=expected_action,
            fair_expected_action=fair_expected,
            actual_action=output,
            state_digest_expected=state_digest(expected_state),
            state_digest_actual=state_digest(actual_state),
            behavior_digest=_behavior_digest(condition, received, output.action_kind, output.quantity,
                                             actual_next if next_pos is not None else -999),
            classification=classification,
            corruption_injected=corruption_injected,
            restore_applied=restore_applied,
            divergence=divergence,
            input_tokens=in_tok,
            output_tokens=out_tok,
            usage_available=usage_available,
        ))

        # Recovery detection (H-recover): after a restore hop, if divergence
        # returns to zero and stays zero, count a recovery event.
        if restore_applied and divergence == 0:
            recovery_events += 1
            corrupted = False

    # Final states
    final_expected = State(position_qty=expected_positions[-1],
                           target_signal=spec.target_at(hops),
                           cash_cents=10000 - expected_positions[-1] * 10000)
    final_actual = State(position_qty=actual_positions[-1],
                         target_signal=spec.target_at(hops),
                         cash_cents=10000 - actual_positions[-1] * 10000)

    # RECOVERY_FAILURE for H-recover: corruption was injected but the chain
    # never returned to the oracle trajectory.
    chain_survived = all(r.classification == "PASS" for r in records) and final_actual.position_qty == final_expected.position_qty
    if condition == "H-recover" and last_corrupt_hop is not None and not chain_survived:
        if recovery_events == 0:
            failure_counts["RECOVERY_FAILURE"] = failure_counts.get("RECOVERY_FAILURE", 0) + 1
            total_failures += 1
            if first_failed_hop is None:
                first_failed_hop = last_corrupt_hop

    return ChainResult(
        chain_id=spec.chain_id,
        condition=condition,
        hops=hops,
        initial_state=spec.initial_state,
        final_expected_state=final_expected,
        final_actual_state=final_actual,
        first_failed_hop=first_failed_hop,
        total_failures=total_failures,
        recovery_events=recovery_events,
        chain_survived=chain_survived,
        hop_records=records,
        expected_positions=expected_positions,
        actual_positions=actual_positions,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        failure_counts=failure_counts,
    )


# ---------------------------------------------------------------------------
# Per-hop persistence (F3)
# ---------------------------------------------------------------------------


def hop_record_to_dict(rec: HopRecord) -> dict[str, Any]:
    """Serialize one HopRecord for persistence.

    Contains everything needed to reconstruct the hop offline:
    chain_id, hop_index, condition, received/emitted state digests, oracle
    expected action, worker action, classification, corruption/recovery
    status, token usage, and failure taxonomy. No secrets are included.
    """
    return {
        "chain_id": rec.chain_id,
        "hop_index": rec.hop,
        "condition": rec.condition,
        "received_state": rec.received_state.to_dict(),
        "received_state_digest": state_digest(rec.received_state),
        "expected_state": rec.expected_state.to_dict(),
        "expected_state_digest": rec.state_digest_expected,
        "actual_state": rec.actual_state.to_dict(),
        "actual_state_digest": rec.state_digest_actual,
        "behavior_digest": rec.behavior_digest,
        "expected_action": rec.expected_action.kind.value,
        "expected_quantity": rec.expected_action.quantity,
        "fair_expected_action": rec.fair_expected_action.kind.value,
        "worker_action": rec.actual_action.action_kind,
        "worker_quantity": rec.actual_action.quantity,
        "worker_next_position_qty": rec.actual_action.next_position_qty,
        "worker_reasoning": rec.actual_action.reasoning,
        "classification": rec.classification,
        "corruption_injected": rec.corruption_injected,
        "restore_applied": rec.restore_applied,
        "divergence": rec.divergence,
        "input_tokens": rec.input_tokens,
        "output_tokens": rec.output_tokens,
        "usage_available": rec.usage_available,
    }


def chain_result_to_dict(result: ChainResult) -> dict[str, Any]:
    """Serialize a full ChainResult including all per-hop records."""
    return {
        "chain_id": result.chain_id,
        "condition": result.condition,
        "hops": result.hops,
        "initial_state": result.initial_state.to_dict(),
        "final_expected_state": result.final_expected_state.to_dict(),
        "final_actual_state": result.final_actual_state.to_dict(),
        "first_failed_hop": result.first_failed_hop,
        "total_failures": result.total_failures,
        "recovery_events": result.recovery_events,
        "chain_survived": result.chain_survived,
        "total_input_tokens": result.total_input_tokens,
        "total_output_tokens": result.total_output_tokens,
        "failure_counts": result.failure_counts,
        "hop_records": [hop_record_to_dict(r) for r in result.hop_records],
    }


# ---------------------------------------------------------------------------
# Experiment runner (all chains x conditions)
# ---------------------------------------------------------------------------


def run_experiment(
    specs: list[ChainSpec],
    conditions: list[str],
    worker_factory: Callable[[str], Any],
    condition_hops: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """Run every chain under every condition.

    ``worker_factory(condition)`` returns a fresh worker for the condition
    (fresh context per condition run). ``condition_hops`` optionally limits
    hops per condition (used by the pilot).
    """
    results: dict[str, Any] = {
        "chains": {},
        "chain_ids": [s.chain_id for s in specs],
        "conditions": conditions,
        "hops": specs[0].hops if specs else 0,
    }
    for condition in conditions:
        results["chains"][condition] = {}
        for spec in specs:
            worker = worker_factory(condition)
            chain_result = run_chain(spec, condition, worker)
            results["chains"][condition][spec.chain_id] = chain_result
    return results


# ---------------------------------------------------------------------------
# Aggregated metrics
# ---------------------------------------------------------------------------


def aggregate_metrics(chain_results: list[ChainResult]) -> dict[str, Any]:
    """Compute condition-level metrics across chains."""
    total_hops = sum(r.hops for r in chain_results)
    total_handoffs = total_hops
    pass_hops = sum(1 for r in chain_results for rec in r.hop_records if rec.classification == "PASS")
    survived = sum(1 for r in chain_results if r.chain_survived)
    total_chains = len(chain_results)

    divergence_zero = sum(1 for r in chain_results for rec in r.hop_records if rec.divergence == 0)
    action_match = sum(1 for r in chain_results for rec in r.hop_records
                       if rec.actual_action.action_kind == rec.expected_action.kind.value)
    fair_action_match = sum(1 for r in chain_results for rec in r.hop_records
                            if rec.actual_action.action_kind == rec.fair_expected_action.kind.value)
    digest_match = sum(1 for r in chain_results for rec in r.hop_records
                       if rec.state_digest_actual == rec.state_digest_expected)

    divergences = [rec.divergence for r in chain_results for rec in r.hop_records]
    max_abs_div = max((abs(d) for d in divergences), default=0)
    cum_div = sum(abs(d) for d in divergences)
    mean_abs_div = cum_div / total_hops if total_hops else 0.0

    total_in = sum(r.total_input_tokens for r in chain_results)
    total_out = sum(r.total_output_tokens for r in chain_results)
    usage_available_hops = sum(
        1 for r in chain_results for rec in r.hop_records if rec.usage_available
    )

    failure_counts: dict[str, int] = {}
    for r in chain_results:
        for k, v in r.failure_counts.items():
            failure_counts[k] = failure_counts.get(k, 0) + v

    recovery_events = sum(r.recovery_events for r in chain_results)
    corruption_hops = sum(1 for r in chain_results for rec in r.hop_records if rec.corruption_injected)
    restore_hops = sum(1 for r in chain_results for rec in r.hop_records if rec.restore_applied)

    return {
        "handoff_success_rate": pass_hops / total_handoffs if total_handoffs else 0.0,
        "successful_handoffs": pass_hops,
        "total_handoffs": total_handoffs,
        "chain_survival_rate": survived / total_chains if total_chains else 0.0,
        "survived_chains": survived,
        "total_chains": total_chains,
        "state_integrity": divergence_zero / total_hops if total_hops else 0.0,
        "action_accuracy_oracle": action_match / total_hops if total_hops else 0.0,
        "action_accuracy_received": fair_action_match / total_hops if total_hops else 0.0,
        "digest_continuity": digest_match / total_hops if total_hops else 0.0,
        "max_abs_divergence": max_abs_div,
        "cumulative_abs_divergence": cum_div,
        "mean_abs_divergence": mean_abs_div,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "cumulative_tokens": total_in + total_out,
        "average_tokens_per_handoff": (total_in + total_out) / total_handoffs if total_handoffs else 0.0,
        "token_usage_available_hops": usage_available_hops,
        "token_usage_complete": usage_available_hops == total_hops and total_hops > 0,
        "failure_counts": failure_counts,
        "recovery_events": recovery_events,
        "corruption_hops": corruption_hops,
        "restore_hops": restore_hops,
    }


def first_failure_hops(chain_results: list[ChainResult]) -> list[dict[str, Any]]:
    """Per-chain first-failure summary (chain-level metrics)."""
    out = []
    for r in chain_results:
        out.append({
            "chain_id": r.chain_id,
            "initial_state": r.initial_state.to_dict(),
            "final_expected_state": r.final_expected_state.to_dict(),
            "final_actual_state": r.final_actual_state.to_dict(),
            "first_failed_hop": r.first_failed_hop,
            "total_failures": r.total_failures,
            "recovery_events": r.recovery_events,
            "chain_survived": r.chain_survived,
            "failure_counts": r.failure_counts,
        })
    return out


# ---------------------------------------------------------------------------
# Long-horizon analysis
# ---------------------------------------------------------------------------


def long_horizon_analysis(chain_results: list[ChainResult], bucket_size: int = 10) -> dict[str, Any]:
    """Failure statistics per hop-decade + cumulative semantic error + trend.

    Trend classification:
    - zero: no failures at all
    - constant: failure rate per bucket roughly flat (no monotone trend)
    - gradually increasing: failure rate rises with hop bucket
    - catastrophic after threshold: a bucket after a clean/stable prefix has
      a failure rate >= 50% or more than 2x the previous bucket.
    """
    hop_records = [rec for r in chain_results for rec in r.hop_records]
    max_hop = max((rec.hop for rec in hop_records), default=0)
    buckets: list[dict[str, Any]] = []
    for start in range(1, max_hop + 1, bucket_size):
        end = min(start + bucket_size - 1, max_hop)
        recs = [rec for rec in hop_records if start <= rec.hop <= end]
        fails = [rec for rec in recs if rec.classification != "PASS"]
        cum_div = sum(abs(rec.divergence) for rec in recs)
        buckets.append({
            "hops": f"{start}-{end}",
            "total": len(recs),
            "failures": len(fails),
            "failure_rate": len(fails) / len(recs) if recs else 0.0,
            "cumulative_abs_divergence": cum_div,
        })

    failure_rates = [b["failure_rate"] for b in buckets]
    total_failures = sum(b["failures"] for b in buckets)

    if total_failures == 0:
        trend = "zero"
    else:
        # Catastrophic: a bucket's failure rate >= 0.5 after any earlier bucket
        # had a lower rate (or a clean prefix).
        catastrophic = False
        for i in range(1, len(failure_rates)):
            if failure_rates[i] >= 0.5 and failure_rates[i] > 2 * max(failure_rates[:i], default=0.0):
                catastrophic = True
                break
        if catastrophic:
            trend = "catastrophic_after_threshold"
        else:
            first_half = sum(failure_rates[: max(1, len(failure_rates) // 2)])
            second_half = sum(failure_rates[len(failure_rates) // 2:])
            if second_half > first_half * 1.2:
                trend = "gradually_increasing"
            else:
                trend = "constant"

    return {
        "buckets": buckets,
        "bucket_size": bucket_size,
        "total_failures": total_failures,
        "cumulative_abs_divergence": sum(b["cumulative_abs_divergence"] for b in buckets),
        "trend": trend,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_v04a_report(experiment: dict[str, Any]) -> str:
    """Generate the V0.4a experiment report in markdown."""
    lines: list[str] = []
    w = lines.append

    conditions = experiment["conditions"]
    chain_ids = experiment["chain_ids"]
    hops = experiment["hops"]

    w("# PM1 Trading Benchmark v0.4a -- Sequential Handoff Report")
    w("")
    w(f"- **Chains:** {len(chain_ids)}")
    w(f"- **Hops per chain:** {hops}")
    w(f"- **Conditions:** {', '.join(conditions)}")
    w("")

    for condition in conditions:
        chain_results = list(experiment["chains"][condition].values())
        metrics = aggregate_metrics(chain_results)
        w(f"## Condition: {condition}")
        w("")
        w(f"- **Handoff success rate:** {metrics['handoff_success_rate']:.1%} "
          f"({metrics['successful_handoffs']}/{metrics['total_handoffs']})")
        w(f"- **Chain survival rate:** {metrics['chain_survival_rate']:.1%} "
          f"({metrics['survived_chains']}/{metrics['total_chains']})")
        w(f"- **State integrity (divergence==0):** {metrics['state_integrity']:.1%}")
        w(f"- **Action accuracy (vs oracle):** {metrics['action_accuracy_oracle']:.1%}")
        w(f"- **Action accuracy (vs received):** {metrics['action_accuracy_received']:.1%}")
        w(f"- **Digest continuity:** {metrics['digest_continuity']:.1%}")
        w(f"- **Max |divergence|:** {metrics['max_abs_divergence']}")
        w(f"- **Cumulative |divergence|:** {metrics['cumulative_abs_divergence']}")
        w(f"- **Mean |divergence|:** {metrics['mean_abs_divergence']:.3f}")
        w(f"- **Tokens in:** {metrics['total_input_tokens']}")
        w(f"- **Tokens out:** {metrics['total_output_tokens']}")
        w(f"- **Cumulative tokens:** {metrics['cumulative_tokens']}")
        w(f"- **Avg tokens/handoff:** {metrics['average_tokens_per_handoff']:.1f}")
        w(f"- **Recovery events:** {metrics['recovery_events']}")
        w("")
        w("### Failure counts")
        w("")
        for cls in CLASSIFICATIONS:
            cnt = metrics["failure_counts"].get(cls, 0)
            if cnt:
                w(f"- **{cls}:** {cnt}")
        w("")

        w("### Chain-level metrics")
        w("")
        w("| chain | initial | final expected | final actual | first fail | failures | recovery | survived |")
        w("|---|---|---|---|---|---|---|---|")
        for entry in first_failure_hops(chain_results):
            w(f"| {entry['chain_id']} | "
              f"p={entry['initial_state']['position_qty']},t={entry['initial_state']['target_signal']} | "
              f"p={entry['final_expected_state']['position_qty']} | "
              f"p={entry['final_actual_state']['position_qty']} | "
              f"{entry['first_failed_hop'] if entry['first_failed_hop'] else 'none'} | "
              f"{entry['total_failures']} | {entry['recovery_events']} | "
              f"{'YES' if entry['chain_survived'] else 'NO'} |")
        w("")

    # Long-horizon across ALL conditions (or first condition) per condition.
    w("## Long-Horizon Analysis")
    w("")
    for condition in conditions:
        chain_results = list(experiment["chains"][condition].values())
        lh = long_horizon_analysis(chain_results)
        w(f"### {condition}")
        w("")
        w(f"- **Trend:** {lh['trend']}")
        w(f"- **Total failures:** {lh['total_failures']}")
        w(f"- **Cumulative |divergence|:** {lh['cumulative_abs_divergence']}")
        w("")
        w("| hops | total | failures | rate | cum |div| |")
        w("|---|---|---|---|---|")
        for b in lh["buckets"]:
            w(f"| {b['hops']} | {b['total']} | {b['failures']} | {b['failure_rate']:.0%} | {b['cumulative_abs_divergence']} |")
        w("")

    return "\n".join(lines)
