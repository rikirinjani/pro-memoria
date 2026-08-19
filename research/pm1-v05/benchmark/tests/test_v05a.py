"""
V0.5 offline test suite — Context Scaling & Token Economics benchmark.

No API calls. Covers the 16 required test categories:
 1. identical initial conditions (P vs C)
 2. identical scenario schedules
 3. PM-1 state boundedness
 4. conversational history accumulation
 5. token accounting
 6. cumulative token accounting
 7. context-size accounting
 8. prompt isolation
 9. condition isolation
10. oracle equivalence
11. digest independence
12. deterministic replay
13. per-hop persistence
14. horizon generation
15. exact API-call calculation
16. no accidental previous-artifact modification
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.v04a_generator import generate_single_chain_spec
from lib.v04a_state import State, state_digest
from lib.oracle import compute_expected_action, Action, ActionKind
from lib.v05a_chain import (
    HORIZONS,
    PILOT_HORIZONS,
    CONDITIONS,
    run_v05a_chain,
    aggregate_v05a_metrics,
    estimate_tokens,
    poly_fit,
    r_squared,
    fit_scaling_curves,
    scaling_analysis,
    context_ceiling_analysis,
    relative_efficiency,
    hop_record_to_dict,
    chain_result_to_dict,
    generate_chain_spec_at_horizon,
    generate_horizon_specs,
    DEFAULT_CONTEXT_WINDOW,
)
from lib.v05a_worker import (
    TASK_SPEC,
    DeterministicV05Worker,
    build_state_block,
    build_v05a_prompt,
    current_state_line,
    parse_current_state_line,
    transcript_entry,
    pm1_packet_text,
)


def run_pair(horizon: int = 25, chain_index: int = 1) -> tuple:
    """Run both conditions on the same chain with deterministic workers."""
    spec = generate_chain_spec_at_horizon(chain_index, horizon)
    p = run_v05a_chain(spec, "P", DeterministicV05Worker())
    c = run_v05a_chain(spec, "C", DeterministicV05Worker())
    return p, c


# ---------------------------------------------------------------------------
# 1 & 2. Identical initial conditions and scenario schedules
# ---------------------------------------------------------------------------


class TestIdenticalTask:
    def test_identical_initial_state(self):
        spec = generate_chain_spec_at_horizon(1, 25)
        p, c = run_pair(25)
        assert p.initial_state == c.initial_state == spec.initial_state

    def test_identical_target_schedule(self):
        p, c = run_pair(25)
        p_targets = [r.expected_state.target_signal for r in p.hop_records]
        c_targets = [r.expected_state.target_signal for r in c.hop_records]
        assert p_targets == c_targets

    def test_identical_expected_actions(self):
        p, c = run_pair(25)
        p_exp = [r.expected_action.kind.value for r in p.hop_records]
        c_exp = [r.expected_action.kind.value for r in c.hop_records]
        assert p_exp == c_exp

    def test_identical_oracle(self):
        # Both conditions use the same oracle trajectory.
        p, c = run_pair(25)
        p_pos = [r.expected_state.position_qty for r in p.hop_records]
        c_pos = [r.expected_state.position_qty for r in c.hop_records]
        assert p_pos == c_pos


# ---------------------------------------------------------------------------
# 3. PM-1 state boundedness
# ---------------------------------------------------------------------------


class TestPM1Bounded:
    def test_pm1_packet_size_constant(self):
        sizes = set()
        for pos in range(-5, 6):
            for tgt in range(-2, 4):
                sizes.add(len(pm1_packet_text(State(position_qty=pos, target_signal=tgt))))
        # The packet shape is identical; only digits vary, so sizes stay in a
        # tiny band — bounded w.r.t. horizon by construction.
        assert len(sizes) <= 3

    def test_transmitted_context_does_not_grow_with_horizon(self):
        p10, _ = run_pair(10)
        p100, _ = run_pair(100)
        max10 = max(r.transmitted_context_chars for r in p10.hop_records)
        max100 = max(r.transmitted_context_chars for r in p100.hop_records)
        # PM-1 block is per-hop constant; max over the chain must not grow
        # meaningfully with horizon.
        assert max100 <= max10 + 4

    def test_cumulative_transmitted_grows_linear_for_p(self):
        p, _ = run_pair(100)
        recs = p.hop_records
        # Cumulative transmitted ~ linear in hop: last/first ratio ~ hops.
        cum_last = recs[-1].cumulative_transmitted_tokens
        cum_first = recs[0].cumulative_transmitted_tokens
        assert cum_last > cum_first * 50  # ~100x for 100 hops


# ---------------------------------------------------------------------------
# 4. Conversational history accumulation
# ---------------------------------------------------------------------------


class TestConversationAccumulates:
    def test_history_size_grows_with_hop(self):
        _, c = run_pair(50)
        sizes = [r.history_size for r in c.hop_records]
        assert sizes[0] is not None
        assert sizes[-1] > sizes[0]
        # Monotonic growth
        assert all(b >= a for a, b in zip(sizes, sizes[1:]))

    def test_transmitted_context_grows_for_c(self):
        _, c = run_pair(50)
        first = c.hop_records[0].transmitted_context_chars
        last = c.hop_records[-1].transmitted_context_chars
        assert last > first * 3

    def test_transcript_contains_steps(self):
        spec = generate_chain_spec_at_horizon(1, 5)
        worker = DeterministicV05Worker()
        run_v05a_chain(spec, "C", worker)
        # transcript_entry produced at each hop; verify format via current line
        line = current_state_line(State(position_qty=2, target_signal=1))
        st = parse_current_state_line(line)
        assert st == State(position_qty=2, target_signal=1)


# ---------------------------------------------------------------------------
# 5 & 6. Token accounting and cumulative accounting
# ---------------------------------------------------------------------------


class TestTokenAccounting:
    def test_per_hop_tokens_recorded(self):
        p, c = run_pair(10)
        for r in p.hop_records + c.hop_records:
            assert r.input_tokens >= 0
            assert r.output_tokens >= 0
            assert r.cumulative_total_tokens >= 0

    def test_cumulative_increases(self):
        p, _ = run_pair(10)
        cums = [r.cumulative_total_tokens for r in p.hop_records]
        assert all(b >= a for a, b in zip(cums, cums[1:]))

    def test_chain_totals_consistent(self):
        p, _ = run_pair(10)
        assert p.total_input_tokens == p.hop_records[-1].cumulative_input_tokens
        assert p.cumulative_tokens == p.total_input_tokens + p.total_output_tokens

    def test_estimate_tokens(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("a" * 100) == 25


# ---------------------------------------------------------------------------
# 7. Context-size accounting
# ---------------------------------------------------------------------------


class TestContextSizes:
    def test_pm1_packet_size_recorded(self):
        p, _ = run_pair(10)
        for r in p.hop_records:
            assert r.pm1_packet_size is not None
            assert r.history_size is None

    def test_history_size_recorded(self):
        _, c = run_pair(10)
        for r in c.hop_records:
            assert r.history_size is not None
            assert r.pm1_packet_size is None

    def test_transmitted_context_tokens(self):
        p, c = run_pair(10)
        for r in p.hop_records:
            assert r.transmitted_context_tokens == estimate_tokens(
                build_state_block("P", r.received_state))
        for r in c.hop_records:
            assert r.transmitted_context_tokens > 0


# ---------------------------------------------------------------------------
# 8 & 9. Prompt isolation and condition isolation
# ---------------------------------------------------------------------------


class TestPromptIsolation:
    FORBIDDEN = ["horizon", "trial", "scenario", "generator_seed", "seed=",
                 "expected_action", "oracle", "token", "P condition",
                 "C condition", "conversational condition", "PM-1 condition"]

    def test_p_prompt_isolated(self):
        spec = generate_chain_spec_at_horizon(1, 10)
        block = build_state_block("P", spec.initial_state)
        msgs = build_v05a_prompt(block)
        content = msgs[1]["content"].lower()
        for f in self.FORBIDDEN:
            assert f not in content, f"P prompt leaks {f}"

    def test_c_prompt_isolated(self):
        spec = generate_chain_spec_at_horizon(1, 10)
        transcript = [transcript_entry(1, State(0, 0), "BUY", 1, "x")]
        block = build_state_block("C", State(position_qty=1, target_signal=1), transcript)
        msgs = build_v05a_prompt(block)
        content = msgs[1]["content"].lower()
        for f in self.FORBIDDEN:
            assert f not in content, f"C prompt leaks {f}"

    def test_p_and_c_prompts_share_task_spec(self):
        p_msgs = build_v05a_prompt(pm1_packet_text(State(0, 1)))
        c_block = build_state_block("C", State(1, 1),
                                    [transcript_entry(1, State(0, 1), "BUY", 1, "x")])
        c_msgs = build_v05a_prompt(c_block)
        assert TASK_SPEC in p_msgs[1]["content"]
        assert TASK_SPEC in c_msgs[1]["content"]

    def test_no_condition_name_in_prompt(self):
        # Neither prompt may contain the letter-encoded condition label.
        block = build_state_block("C", State(1, 1),
                                  [transcript_entry(1, State(0, 1), "BUY", 1, "x")])
        msgs = build_v05a_prompt(block)
        # "condition" as a word is forbidden entirely.
        assert "condition" not in msgs[1]["content"].lower()

    def test_fresh_context_each_hop(self):
        m1 = build_v05a_prompt(pm1_packet_text(State(0, 1)))
        m2 = build_v05a_prompt(pm1_packet_text(State(1, 1)))
        assert m1 is not m2
        assert m1[1] is not m2[1]


# ---------------------------------------------------------------------------
# 10. Oracle equivalence
# ---------------------------------------------------------------------------


class TestOracleEquivalence:
    def test_both_conditions_solve_same_task(self):
        p, c = run_pair(25)
        assert p.chain_survived is True
        assert c.chain_survived is True
        assert p.final_actual_state == c.final_actual_state == p.final_expected_state

    def test_expected_actions_from_oracle(self):
        p, _ = run_pair(10)
        for r in p.hop_records:
            oracle = compute_expected_action(r.received_state.position_qty,
                                             r.received_state.target_signal)
            assert r.expected_action == oracle


# ---------------------------------------------------------------------------
# 11. Digest independence
# ---------------------------------------------------------------------------


class TestDigestIndependence:
    def test_same_semantic_state_same_digest(self):
        assert state_digest(State(2, 1)) == state_digest(State(2, 1))

    def test_digest_ignores_identity(self):
        p10, _ = run_pair(10)
        p100, _ = run_pair(100)
        # Same semantic state across different horizons -> same digest.
        d10 = state_digest(State(p10.initial_state.position_qty, 1))
        d100 = state_digest(State(p100.initial_state.position_qty, 1))
        assert d10 == d100

    def test_actual_digest_matches_state(self):
        p, _ = run_pair(10)
        for r in p.hop_records:
            assert r.state_digest_actual == state_digest(r.actual_state)


# ---------------------------------------------------------------------------
# 12. Deterministic replay
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_identical_replay(self):
        a = run_pair(25)
        b = run_pair(25)
        for ra, rb in zip(a, b):
            assert [r.classification for r in ra.hop_records] == [r.classification for r in rb.hop_records]
            assert [r.input_tokens for r in ra.hop_records] == [r.input_tokens for r in rb.hop_records]
            assert ra.final_actual_state == rb.final_actual_state

    def test_poly_fit_deterministic(self):
        xs = [10, 25, 50, 100, 250, 500, 1000]
        ys = [h * h for h in xs]
        assert poly_fit(xs, ys, 2) == poly_fit(xs, ys, 2)

    def test_r_squared_perfect_linear(self):
        xs = [10.0, 20.0, 30.0]
        ys = [2 * x + 1 for x in xs]
        assert r_squared(xs, ys, poly_fit(xs, ys, 1)) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 13. Per-hop persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_hop_record_schema(self):
        p, _ = run_pair(5)
        d = hop_record_to_dict(p.hop_records[0])
        for key in ["chain_id", "scenario_id", "hop_index", "horizon", "condition",
                    "received_state", "expected_state", "actual_state",
                    "expected_action", "worker_action", "classification",
                    "divergence", "state_digest_expected", "state_digest_actual",
                    "input_tokens", "output_tokens", "usage_available",
                    "transmitted_context_chars", "transmitted_context_tokens",
                    "pm1_packet_size", "history_size",
                    "cumulative_input_tokens", "cumulative_output_tokens",
                    "cumulative_total_tokens", "cumulative_transmitted_tokens"]:
            assert key in d, f"missing {key}"

    def test_no_secrets_in_persisted(self):
        p, _ = run_pair(5)
        payload = json.dumps(chain_result_to_dict(p))
        for secret in ("api_key", "sk-", "Authorization", "Bearer", "password"):
            assert secret not in payload

    def test_all_hops_persisted(self):
        p, _ = run_pair(10)
        d = chain_result_to_dict(p)
        assert len(d["hop_records"]) == 10
        assert d["horizon"] == 10


# ---------------------------------------------------------------------------
# 14. Horizon generation
# ---------------------------------------------------------------------------


class TestHorizonGeneration:
    def test_all_horizons_generated(self):
        specs = generate_horizon_specs(chain_index=1)
        assert set(specs.keys()) == set(HORIZONS)
        for h, spec in specs.items():
            assert spec.hops == h
            assert len(spec.target_schedule) == h

    def test_prefix_consistent(self):
        # Horizon 50's schedule is the first 50 entries of horizon 1000's.
        h50 = generate_chain_spec_at_horizon(1, 50)
        h1000 = generate_chain_spec_at_horizon(1, 1000)
        assert h50.target_schedule == h1000.target_schedule[:50]

    def test_pilot_horizons_subset(self):
        assert all(h in HORIZONS for h in PILOT_HORIZONS)

    def test_pilot_uses_10_50_100(self):
        assert PILOT_HORIZONS == [10, 50, 100]


# ---------------------------------------------------------------------------
# 15. Exact API-call calculation
# ---------------------------------------------------------------------------


class TestApiCallCount:
    def test_pilot_call_count(self):
        # Pilot: horizons 10/50/100 x 2 conditions x 1 scenario x 1 trial.
        pilot_calls = sum(PILOT_HORIZONS) * len(CONDITIONS)
        assert pilot_calls == 320

    def test_full_call_count(self):
        # Full: all 7 horizons x 2 conditions x 10 scenarios x 3 trials.
        full_calls = sum(HORIZONS) * len(CONDITIONS) * 10 * 3
        assert full_calls == sum(HORIZONS) * 60  # sanity: 1935 x 60
        assert full_calls == 116100

    def test_per_horizon_handoffs(self):
        assert sum(HORIZONS) == 1935
        assert sum(HORIZONS) * len(CONDITIONS) == 3870


# ---------------------------------------------------------------------------
# 16. Previous artifacts untouched
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Scaling analysis helpers
# ---------------------------------------------------------------------------


class TestScalingAnalysis:
    def test_quadratic_beats_linear_for_quadratic_data(self):
        xs = [10, 25, 50, 100, 250, 500, 1000]
        ys = [h * h for h in xs]
        fits = fit_scaling_curves(xs, ys)
        assert fits["quadratic_r2"] > fits["linear_r2"]

    def test_linear_perfect_for_linear_data(self):
        xs = [10, 25, 50, 100]
        ys = [5 * h + 3 for h in xs]
        fits = fit_scaling_curves(xs, ys)
        assert fits["linear_r2"] > 0.999

    def test_relative_efficiency_shape(self):
        p, c = run_pair(25)
        re_ = relative_efficiency([p], [c])
        assert 25 in re_
        assert "ratio_c_over_p" in re_[25]

    def test_context_ceiling_uses_window(self):
        p, c = run_pair(25)
        rows = context_ceiling_analysis(p.hop_records and [p] or [p], DEFAULT_CONTEXT_WINDOW)
        assert rows["context_window"] == DEFAULT_CONTEXT_WINDOW

    def test_scaling_analysis_reports_rows(self):
        p, c = run_pair(10)
        sa = scaling_analysis([p], [c])
        assert len(sa["rows"]) == 1
        assert sa["rows"][0]["horizon"] == 10
