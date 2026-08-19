"""
V0.5 Context Scaling & Token Economics benchmark — chain runner and analysis.

Executes the SAME deterministic task under two handoff conditions:

Condition P (PM-1 state handoff):  bounded PM-1 packet, constant size per hop.
Condition C (conversational handoff): accumulated transcript, grows with hop.

Measures, per handoff: token usage (input/output/total, cumulative), context
sizes (transmitted, max, cumulative; PM-1 packet size; conversation history
size), and reliability (action/received/oracle correctness, state integrity,
digest continuity, drift, survival, parse errors).

Scaling analysis fits linear and quadratic models to cumulative tokens vs
horizon (pure-python least squares, no numpy dependency) and reports growth
ratios and tokens/handoff. The conclusion follows the measured data — the
benchmark does NOT assume PM-1 wins.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from lib.oracle import Action, ActionKind, compute_expected_action
from lib.v04a_generator import ChainSpec, generate_chain_specs, generate_single_chain_spec
from lib.v04a_state import State, state_digest
from lib.v05a_worker import (
    TASK_SPEC,
    build_state_block,
    current_state_line,
    pm1_packet_text,
    transcript_entry,
    HandoffOutput,
)

__all__ = [
    "HORIZONS",
    "PILOT_HORIZONS",
    "generate_horizon_specs",
    "generate_chain_spec_at_horizon",
    "V05HopRecord",
    "V05ChainResult",
    "run_v05a_chain",
    "aggregate_v05a_metrics",
    "estimate_tokens",
    "poly_fit",
    "fit_scaling_curves",
    "scaling_analysis",
    "context_ceiling_analysis",
    "relative_efficiency",
    "hop_record_to_dict",
    "chain_result_to_dict",
    "generate_v05a_report",
]

HORIZONS = [10, 25, 50, 100, 250, 500, 1000]
PILOT_HORIZONS = [10, 50, 100]
CONDITIONS = ["P", "C"]

# Default model context window (tokens). Configurable; set to the provider's
# real window for the run. deepseek-v4-flash window is documented in the
# pre-experiment report.
DEFAULT_CONTEXT_WINDOW = 65536


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate (chars/4). Used offline and when the
    provider omits usage; real runs prefer provider-reported tokens."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Horizon generation (prefix-consistent)
# ---------------------------------------------------------------------------


def generate_chain_spec_at_horizon(
    chain_index: int,
    horizon: int,
    base_seed: int = 42,
    chain_count: int = 10,
    master_hops: int = 1000,
) -> ChainSpec:
    """A chain spec truncated to *horizon* hops.

    Generates a master spec at *master_hops* (default 1000) and truncates the
    target schedule, so every horizon evaluates a prefix of the SAME
    deterministic task.
    """
    master = generate_single_chain_spec(chain_index, base_seed, master_hops, chain_count)
    return replace(
        master,
        target_schedule=master.target_schedule[:horizon],
        scenario_metadata=dict(master.scenario_metadata, horizon=horizon),
    )


def generate_horizon_specs(
    horizons: list[int] | None = None,
    chain_index: int = 1,
    base_seed: int = 42,
    chain_count: int = 10,
) -> dict[int, ChainSpec]:
    """One spec per horizon (same chain) for a single scenario."""
    horizons = horizons or HORIZONS
    return {
        h: generate_chain_spec_at_horizon(chain_index, h, base_seed, chain_count)
        for h in horizons
    }


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class V05HopRecord:
    chain_id: str
    scenario_id: str
    hop_index: int
    horizon: int
    condition: str  # "P" or "C"
    received_state: State
    expected_state: State
    actual_state: State
    expected_action: Action
    worker_action: str
    worker_quantity: int
    classification: str
    divergence: int
    state_digest_expected: str
    state_digest_actual: str
    # token metrics
    input_tokens: int
    output_tokens: int
    usage_available: bool
    # context metrics
    transmitted_context_chars: int
    transmitted_context_tokens: int
    pm1_packet_size: int | None  # chars, P only
    history_size: int | None     # chars, C only
    cumulative_input_tokens: int
    cumulative_output_tokens: int
    cumulative_total_tokens: int
    cumulative_transmitted_tokens: int


@dataclass
class V05ChainResult:
    chain_id: str
    scenario_id: str
    condition: str
    horizon: int
    initial_state: State
    final_expected_state: State
    final_actual_state: State
    first_failed_hop: int | None
    total_failures: int
    chain_survived: bool
    hop_records: list[V05HopRecord] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cumulative_tokens: int = 0
    cumulative_transmitted_tokens: int = 0
    max_transmitted_tokens: int = 0
    failure_counts: dict[str, int] = field(default_factory=dict)


def _classify(worker_action: str, fair_action: Action, divergence: int) -> str:
    if worker_action == "PARSE_ERROR":
        return "PARSE_ERROR"
    if worker_action != fair_action.kind.value:
        return "ACTION_ERROR"
    if divergence != 0:
        return "STATE_CORRUPTION"
    return "PASS"


def run_v05a_chain(
    spec: ChainSpec,
    condition: str,
    worker: Any,
    task_spec: str = TASK_SPEC,
) -> V05ChainResult:
    """Run one chain (truncated to spec.hops) under one condition.

    ``worker`` exposes ``run(state_block, condition, task_spec) -> HandoffOutput``
    and ``last_usage`` (dict of prompt_tokens/completion_tokens).
    """
    hops = spec.hops
    expected_positions = [spec.initial_state.position_qty]
    actual_pos = spec.initial_state.position_qty

    records: list[V05HopRecord] = []
    failure_counts: dict[str, int] = {}
    first_failed_hop: int | None = None
    total_failures = 0
    total_in = total_out = 0
    cumulative_transmitted = 0
    max_transmitted = 0

    transcript: list[str] = []

    for hop in range(1, hops + 1):
        target = spec.target_at(hop)
        expected_pos = expected_positions[-1]
        expected_action = compute_expected_action(expected_pos, target)
        delta = 1 if expected_action.kind is ActionKind.BUY else (-1 if expected_action.kind is ActionKind.SELL else 0)
        expected_next = expected_pos + delta
        expected_positions.append(expected_next)

        received = State(position_qty=actual_pos, target_signal=target,
                         cash_cents=10000 - actual_pos * 10000)

        # Build the worker-visible state block for this condition.
        state_block = build_state_block(condition, received, transcript)
        block_chars = len(state_block)
        block_tokens = estimate_tokens(state_block)
        pm1_size = len(pm1_packet_text(received)) if condition == "P" else None
        history_size = len("\n".join(transcript)) if condition == "C" else None

        try:
            output = worker.run(state_block, condition, task_spec)
        except Exception as exc:
            output = HandoffOutput("PARSE_ERROR", 0, None,
                                   reasoning=f"worker exception: {exc}", parse_error=True)
            next_pos = actual_pos
        else:
            next_pos = output.next_position_qty

        fair_action = compute_expected_action(actual_pos, target)
        actual_next = next_pos if next_pos is not None else actual_pos
        divergence = actual_next - expected_next

        classification = _classify(output.action_kind, fair_action, divergence)
        failure_counts[classification] = failure_counts.get(classification, 0) + 1
        if classification != "PASS":
            total_failures += 1
            if first_failed_hop is None:
                first_failed_hop = hop

        actual_state = State(position_qty=actual_next, target_signal=target,
                             cash_cents=10000 - actual_next * 10000)
        actual_pos = actual_next

        usage = getattr(worker, "last_usage", None) or {}
        if usage:
            in_tok = int(usage.get("prompt_tokens", 0))
            out_tok = int(usage.get("completion_tokens", 0))
            usage_available = True
        else:
            in_tok = block_tokens  # offline estimate
            out_tok = estimate_tokens(output.reasoning)
            usage_available = False
        total_in += in_tok
        total_out += out_tok
        cumulative_transmitted += block_tokens
        max_transmitted = max(max_transmitted, block_tokens)

        records.append(V05HopRecord(
            chain_id=spec.chain_id,
            scenario_id=str(spec.scenario_metadata.get("chain_index", 1)),
            hop_index=hop,
            horizon=hops,
            condition=condition,
            received_state=received,
            expected_state=State(position_qty=expected_next, target_signal=target,
                                 cash_cents=10000 - expected_next * 10000),
            actual_state=actual_state,
            expected_action=expected_action,
            worker_action=output.action_kind,
            worker_quantity=output.quantity,
            classification=classification,
            divergence=divergence,
            state_digest_expected=state_digest(expected_state_placeholder(expected_next, target)),
            state_digest_actual=state_digest(actual_state),
            input_tokens=in_tok,
            output_tokens=out_tok,
            usage_available=usage_available,
            transmitted_context_chars=block_chars,
            transmitted_context_tokens=block_tokens,
            pm1_packet_size=pm1_size,
            history_size=history_size,
            cumulative_input_tokens=total_in,
            cumulative_output_tokens=total_out,
            cumulative_total_tokens=total_in + total_out,
            cumulative_transmitted_tokens=cumulative_transmitted,
        ))

        # Append this step to the conversation transcript for condition C.
        transcript.append(transcript_entry(
            hop, received, output.action_kind, output.quantity, output.reasoning,
        ))

    final_expected = State(position_qty=expected_positions[-1],
                           target_signal=spec.target_at(hops),
                           cash_cents=10000 - expected_positions[-1] * 10000)
    final_actual = State(position_qty=actual_pos, target_signal=spec.target_at(hops),
                         cash_cents=10000 - actual_pos * 10000)
    chain_survived = all(r.classification == "PASS" for r in records) and final_actual == final_expected

    return V05ChainResult(
        chain_id=spec.chain_id,
        scenario_id=str(spec.scenario_metadata.get("chain_index", 1)),
        condition=condition,
        horizon=hops,
        initial_state=spec.initial_state,
        final_expected_state=final_expected,
        final_actual_state=final_actual,
        first_failed_hop=first_failed_hop,
        total_failures=total_failures,
        chain_survived=chain_survived,
        hop_records=records,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        cumulative_tokens=total_in + total_out,
        cumulative_transmitted_tokens=cumulative_transmitted,
        max_transmitted_tokens=max_transmitted,
        failure_counts=failure_counts,
    )


def expected_state_placeholder(position: int, target: int) -> State:
    return State(position_qty=position, target_signal=target)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_v05a_metrics(results: list[V05ChainResult]) -> dict[str, Any]:
    total_handoffs = sum(r.horizon for r in results)
    pass_handoffs = sum(1 for r in results for rec in r.hop_records if rec.classification == "PASS")
    survived = sum(1 for r in results if r.chain_survived)
    integrity = sum(1 for r in results for rec in r.hop_records if rec.divergence == 0)
    digest = sum(1 for r in results for rec in r.hop_records
                 if rec.state_digest_actual == rec.state_digest_expected)
    action_match = sum(1 for r in results for rec in r.hop_records
                       if rec.worker_action == rec.expected_action.kind.value)
    usage_avail = sum(1 for r in results for rec in r.hop_records if rec.usage_available)
    fail_counts: dict[str, int] = {}
    for r in results:
        for k, v in r.failure_counts.items():
            fail_counts[k] = fail_counts.get(k, 0) + v
    total_in = sum(r.total_input_tokens for r in results)
    total_out = sum(r.total_output_tokens for r in results)
    return {
        "total_chains": len(results),
        "total_handoffs": total_handoffs,
        "successful_handoffs": pass_handoffs,
        "handoff_success_rate": pass_handoffs / total_handoffs if total_handoffs else 0.0,
        "chain_survival_rate": survived / len(results) if results else 0.0,
        "state_integrity": integrity / total_handoffs if total_handoffs else 0.0,
        "digest_continuity": digest / total_handoffs if total_handoffs else 0.0,
        "action_accuracy_received": action_match / total_handoffs if total_handoffs else 0.0,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "cumulative_tokens": total_in + total_out,
        "token_usage_available_hops": usage_avail,
        "token_usage_complete": usage_avail == total_handoffs and total_handoffs > 0,
        "failure_counts": fail_counts,
    }


# ---------------------------------------------------------------------------
# Scaling analysis (pure-python least squares)
# ---------------------------------------------------------------------------


def poly_fit(xs: list[float], ys: list[float], degree: int) -> list[float]:
    """Least-squares polynomial fit (normal equations). Returns coefficients
    highest-degree-first."""
    n = len(xs)
    if n < degree + 1:
        return [0.0] * (degree + 1)
    # Design matrix columns: x^degree ... x^0
    a = [[x ** (degree - j) for j in range(degree + 1)] for x in xs]
    at = [[a[i][j] for i in range(n)] for j in range(degree + 1)]
    # Normal equations: (A^T A) c = A^T y
    ata = [[sum(at[i][k] * a[k][j] for k in range(n)) for j in range(degree + 1)]
           for i in range(degree + 1)]
    aty = [sum(at[i][k] * ys[k] for k in range(n)) for i in range(degree + 1)]
    # Gaussian elimination
    m = [row[:] + [aty[i]] for i, row in enumerate(ata)]
    for col in range(degree + 1):
        pivot = max(range(col, degree + 1), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        pv = m[col][col]
        if abs(pv) < 1e-12:
            continue
        for r in range(col + 1, degree + 1):
            factor = m[r][col] / pv
            for c in range(col, degree + 2):
                m[r][c] -= factor * m[col][c]
    coef = [0.0] * (degree + 1)
    for i in range(degree, -1, -1):
        s = m[i][degree + 1] - sum(m[i][j] * coef[j] for j in range(i + 1, degree + 1))
        coef[i] = s / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0
    return coef


def r_squared(xs: list[float], ys: list[float], coef: list[float]) -> float:
    n = len(ys)
    mean_y = sum(ys) / n
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot == 0:
        return 1.0
    ss_res = 0.0
    for x, y in zip(xs, ys):
        pred = sum(c * (x ** (len(coef) - 1 - i)) for i, c in enumerate(coef))
        ss_res += (y - pred) ** 2
    return 1.0 - ss_res / ss_tot


def fit_scaling_curves(horizons: list[int], cumulative: list[int]) -> dict[str, Any]:
    """Fit linear and quadratic models to cumulative tokens vs horizon."""
    xs = [float(h) for h in horizons]
    ys = [float(v) for v in cumulative]
    lin = poly_fit(xs, ys, 1)
    quad = poly_fit(xs, ys, 2)
    return {
        "linear_coefficients": lin,
        "linear_r2": r_squared(xs, ys, lin),
        "quadratic_coefficients": quad,
        "quadratic_r2": r_squared(xs, ys, quad),
        "n_points": len(horizons),
    }


def scaling_analysis(
    p_results: list[V05ChainResult],
    c_results: list[V05ChainResult],
    horizons: list[int] | None = None,
) -> dict[str, Any]:
    """Cumulative tokens and context by horizon + fits + growth ratios."""
    horizons = horizons or sorted({r.horizon for r in p_results + c_results})
    cum_p = [sum(r.cumulative_tokens for r in p_results if r.horizon == h) for h in horizons]
    cum_c = [sum(r.cumulative_tokens for r in c_results if r.horizon == h) for h in horizons]
    ctx_p = [sum(r.cumulative_transmitted_tokens for r in p_results if r.horizon == h) for h in horizons]
    ctx_c = [sum(r.cumulative_transmitted_tokens for r in c_results if r.horizon == h) for h in horizons]

    rows = []
    for i, h in enumerate(horizons):
        p_handoffs = sum(r.horizon for r in p_results if r.horizon == h)
        c_handoffs = sum(r.horizon for r in c_results if r.horizon == h)
        rows.append({
            "horizon": h,
            "cumulative_tokens_p": cum_p[i],
            "cumulative_tokens_c": cum_c[i],
            "tokens_per_handoff_p": cum_p[i] / p_handoffs if p_handoffs else 0.0,
            "tokens_per_handoff_c": cum_c[i] / c_handoffs if c_handoffs else 0.0,
            "cumulative_transmitted_p": ctx_p[i],
            "cumulative_transmitted_c": ctx_c[i],
            "ratio_c_over_p": (cum_c[i] / cum_p[i]) if cum_p[i] else None,
            "reduction_1_minus_p_over_c": (1 - cum_p[i] / cum_c[i]) if cum_c[i] else None,
        })

    return {
        "horizons": horizons,
        "rows": rows,
        "token_fits_p": fit_scaling_curves(horizons, cum_p),
        "token_fits_c": fit_scaling_curves(horizons, cum_c),
        "context_fits_p": fit_scaling_curves(horizons, ctx_p),
        "context_fits_c": fit_scaling_curves(horizons, ctx_c),
    }


def relative_efficiency(p_results: list[V05ChainResult], c_results: list[V05ChainResult]) -> dict[str, Any]:
    """Per-horizon cumulative-token ratio and percentage reduction."""
    horizons = sorted({r.horizon for r in p_results + c_results})
    out = {}
    for h in horizons:
        cp = sum(r.cumulative_tokens for r in p_results if r.horizon == h)
        cc = sum(r.cumulative_tokens for r in c_results if r.horizon == h)
        out[h] = {
            "cumulative_p": cp,
            "cumulative_c": cc,
            "ratio_c_over_p": (cc / cp) if cp else None,
            "percent_reduction": (1 - cp / cc) if cc else None,
        }
    return out


def context_ceiling_analysis(
    results: list[V05ChainResult],
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> dict[str, Any]:
    """Max transmitted context per horizon as % of the model context window."""
    horizons = sorted({r.horizon for r in results})
    rows = []
    for h in horizons:
        mx = max(r.max_transmitted_tokens for r in results if r.horizon == h)
        rows.append({
            "horizon": h,
            "max_transmitted_tokens": mx,
            "context_window": context_window,
            "percent_consumed": mx / context_window * 100 if context_window else None,
        })
    return {"context_window": context_window, "rows": rows}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def hop_record_to_dict(rec: V05HopRecord) -> dict[str, Any]:
    return {
        "chain_id": rec.chain_id,
        "scenario_id": rec.scenario_id,
        "hop_index": rec.hop_index,
        "horizon": rec.horizon,
        "condition": rec.condition,
        "received_state": rec.received_state.to_dict(),
        "expected_state": rec.expected_state.to_dict(),
        "actual_state": rec.actual_state.to_dict(),
        "expected_action": rec.expected_action.kind.value,
        "worker_action": rec.worker_action,
        "worker_quantity": rec.worker_quantity,
        "classification": rec.classification,
        "divergence": rec.divergence,
        "state_digest_expected": rec.state_digest_expected,
        "state_digest_actual": rec.state_digest_actual,
        "input_tokens": rec.input_tokens,
        "output_tokens": rec.output_tokens,
        "usage_available": rec.usage_available,
        "transmitted_context_chars": rec.transmitted_context_chars,
        "transmitted_context_tokens": rec.transmitted_context_tokens,
        "pm1_packet_size": rec.pm1_packet_size,
        "history_size": rec.history_size,
        "cumulative_input_tokens": rec.cumulative_input_tokens,
        "cumulative_output_tokens": rec.cumulative_output_tokens,
        "cumulative_total_tokens": rec.cumulative_total_tokens,
        "cumulative_transmitted_tokens": rec.cumulative_transmitted_tokens,
    }


def chain_result_to_dict(r: V05ChainResult) -> dict[str, Any]:
    return {
        "chain_id": r.chain_id,
        "scenario_id": r.scenario_id,
        "condition": r.condition,
        "horizon": r.horizon,
        "initial_state": r.initial_state.to_dict(),
        "final_expected_state": r.final_expected_state.to_dict(),
        "final_actual_state": r.final_actual_state.to_dict(),
        "first_failed_hop": r.first_failed_hop,
        "total_failures": r.total_failures,
        "chain_survived": r.chain_survived,
        "total_input_tokens": r.total_input_tokens,
        "total_output_tokens": r.total_output_tokens,
        "cumulative_tokens": r.cumulative_tokens,
        "cumulative_transmitted_tokens": r.cumulative_transmitted_tokens,
        "max_transmitted_tokens": r.max_transmitted_tokens,
        "failure_counts": r.failure_counts,
        "hop_records": [hop_record_to_dict(rec) for rec in r.hop_records],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_v05a_report(
    p_results: list[V05ChainResult],
    c_results: list[V05ChainResult],
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> str:
    lines: list[str] = []
    w = lines.append
    w("# PM1 Trading Benchmark v0.5 -- Context Scaling & Token Economics")
    w("")
    w(f"- Conditions: P (PM-1 state handoff) vs C (conversational handoff)")
    w(f"- Horizons: {sorted({r.horizon for r in p_results + c_results})}")
    w("")

    mp = aggregate_v05a_metrics(p_results)
    mc = aggregate_v05a_metrics(c_results)

    w("## Reliability summary")
    w("")
    w("| Metric | P (PM-1) | C (conversational) |")
    w("|---|---|---|")
    w(f"| Handoff success | {mp['handoff_success_rate']:.4f} | {mc['handoff_success_rate']:.4f} |")
    w(f"| Chain survival | {mp['chain_survival_rate']:.4f} | {mc['chain_survival_rate']:.4f} |")
    w(f"| State integrity | {mp['state_integrity']:.4f} | {mc['state_integrity']:.4f} |")
    w(f"| Digest continuity | {mp['digest_continuity']:.4f} | {mc['digest_continuity']:.4f} |")
    w(f"| Action accuracy | {mp['action_accuracy_received']:.4f} | {mc['action_accuracy_received']:.4f} |")
    w("")

    w("## Token economics")
    w("")
    w("| Metric | P (PM-1) | C (conversational) |")
    w("|---|---|---|")
    w(f"| Total input tokens | {mp['total_input_tokens']} | {mc['total_input_tokens']} |")
    w(f"| Total output tokens | {mp['total_output_tokens']} | {mc['total_output_tokens']} |")
    w(f"| Cumulative tokens | {mp['cumulative_tokens']} | {mc['cumulative_tokens']} |")
    w("")

    sa = scaling_analysis(p_results, c_results)
    w("## Scaling analysis (cumulative tokens vs horizon)")
    w("")
    w("| horizon | P cum | C cum | C/P | 1-P/C | P tok/hop | C tok/hop |")
    w("|---|---|---|---|---|---|---|")
    for row in sa["rows"]:
        ratio = f"{row['ratio_c_over_p']:.2f}" if row["ratio_c_over_p"] is not None else "-"
        red = f"{row['reduction_1_minus_p_over_c']:.1%}" if row["reduction_1_minus_p_over_c"] is not None else "-"
        w(f"| {row['horizon']} | {row['cumulative_tokens_p']} | {row['cumulative_tokens_c']} | "
          f"{ratio} | {red} | {row['tokens_per_handoff_p']:.1f} | {row['tokens_per_handoff_c']:.1f} |")
    w("")
    w("### Model fits (cumulative tokens)")
    w("")
    for name, fits in (("P", sa["token_fits_p"]), ("C", sa["token_fits_c"])):
        w(f"- **{name}:** linear R^2={fits['linear_r2']:.4f} "
          f"(coef {[round(c, 4) for c in fits['linear_coefficients']]}); "
          f"quadratic R^2={fits['quadratic_r2']:.4f} "
          f"(coef {[round(c, 6) for c in fits['quadratic_coefficients']]})")
    w("")

    ce = context_ceiling_analysis(p_results + c_results, context_window)
    w("## Context ceiling")
    w("")
    w("| horizon | max P ctx (tok) | max C ctx (tok) | % of window (C) |")
    w("|---|---|---|---|")
    for row in ce["rows"]:
        p_mx = max((r.max_transmitted_tokens for r in p_results if r.horizon == row["horizon"]), default=0)
        w(f"| {row['horizon']} | {p_mx} | {row['max_transmitted_tokens']} | "
          f"{row['percent_consumed']:.1f}% |")
    w("")

    re_ = relative_efficiency(p_results, c_results)
    w("## Relative efficiency (per horizon)")
    w("")
    w("| horizon | C/P ratio | reduction 1-P/C |")
    w("|---|---|---|")
    for h in sorted(re_):
        d = re_[h]
        ratio = f"{d['ratio_c_over_p']:.2f}" if d["ratio_c_over_p"] is not None else "-"
        red = f"{d['percent_reduction']:.1%}" if d["percent_reduction"] is not None else "-"
        w(f"| {h} | {ratio} | {red} |")
    w("")
    w("Conclusion follows the measured data. No assumption that PM-1 wins.")
    return "\n".join(lines)
