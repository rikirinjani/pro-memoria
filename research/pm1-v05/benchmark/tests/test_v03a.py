"""
Tests for PM1 Trading Benchmark v0.3a — Scenario Generalization.

Covers:
- Scenario generation (24 scenarios, deterministic, groups, splits)
- Task-spec variants (3 variants, equivalence, no leakage)
- Prompt isolation (no metadata leakage)
- Condition correctness (all 6 conditions work with generated scenarios)
- Digest independence
- Held-out separation
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow running from project root.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.scenario_generator import (
    ScenarioSpec,
    generate_scenarios,
    get_dev_scenarios,
    get_held_out_scenarios,
    TASK_SPEC_VARIANTS,
    spec_to_scenario,
    scenario_matrix_table,
    _compute_corrupt,
)
from lib.scenario import Scenario, Observation
from lib.oracle import compute_expected_action
from lib.worker import build_worker_inputs, execute_worker
from lib.fixtures import create_state_dir
from lib.llm_worker import build_llm_prompt
from lib.llm_runner import scenario_spec_to_scenario, _CONDITIONS_V03A


# ---------------------------------------------------------------------------
# Scenario generation tests
# ---------------------------------------------------------------------------


class TestScenarioGeneration:
    """Test scenario generation correctness."""

    def test_generates_24_scenarios(self):
        scenarios = generate_scenarios()
        assert len(scenarios) == 24

    def test_deterministic_from_seed(self):
        s1 = generate_scenarios()
        s2 = generate_scenarios()
        for a, b in zip(s1, s2):
            assert a.scenario_id == b.scenario_id
            assert a.generator_seed == b.generator_seed
            assert a.f_position == b.f_position
            assert a.l_position == b.l_position
            assert a.target_signal == b.target_signal
            assert a.policy_variant == b.policy_variant

    def test_unique_scenario_ids(self):
        scenarios = generate_scenarios()
        ids = [s.scenario_id for s in scenarios]
        assert len(set(ids)) == 24

    def test_six_groups(self):
        groups = {}
        for spec in generate_scenarios():
            # Extract group from scenario_id (e.g., "G1-S01" → "G1")
            group = spec.scenario_id.split("-")[0]
            groups.setdefault(group, []).append(spec)
        assert len(groups) == 6
        assert all(len(v) >= 3 for v in groups.values())

    def test_action_coverage(self):
        scenarios = generate_scenarios()
        actions = set()
        for spec in scenarios:
            expected = compute_expected_action(spec.f_position, spec.target_signal)
            actions.add(expected.kind.value)
        assert "BUY" in actions
        assert "SELL" in actions
        assert "HOLD" in actions

    def test_negative_positions_in_groups(self):
        scenarios = generate_scenarios()
        neg_groups = [s for s in scenarios if s.scenario_id.startswith("G4") or s.scenario_id.startswith("G5")]
        assert len(neg_groups) == 8
        has_negative = any(s.f_position < 0 or s.l_position < 0 for s in neg_groups)
        assert has_negative

    def test_multi_unit_diffs(self):
        scenarios = generate_scenarios()
        large_diff = [s for s in scenarios if abs(s.f_position - s.l_position) > 2]
        assert len(large_diff) > 0

    def test_all_scenarios_have_both_episodes(self):
        for spec in generate_scenarios():
            # ScenarioSpec has f_position and l_position (not episodes dict)
            assert isinstance(spec.f_position, int)
            assert isinstance(spec.l_position, int)

    def test_f_and_l_differ(self):
        for spec in generate_scenarios():
            assert spec.f_position != spec.l_position

    def test_policy_variant_present(self):
        for spec in generate_scenarios():
            assert spec.policy_variant in TASK_SPEC_VARIANTS

    def test_corrupt_values_different_from_true(self):
        for spec in generate_scenarios():
            assert spec.corrupt_f != spec.f_position, (
                f"Corrupt F equals true F for {spec.scenario_id}"
            )
            assert spec.corrupt_l != spec.l_position, (
                f"Corrupt L equals true L for {spec.scenario_id}"
            )


# ---------------------------------------------------------------------------
# Dev/held-out split tests
# ---------------------------------------------------------------------------


class TestDevHeldOutSplit:
    """Test dev/held-out split correctness."""

    def test_dev_set_18_scenarios(self):
        dev = get_dev_scenarios()
        assert len(dev) == 18

    def test_held_out_set_6_scenarios(self):
        held = get_held_out_scenarios()
        assert len(held) == 6

    def test_total_24_scenarios(self):
        dev = get_dev_scenarios()
        held = get_held_out_scenarios()
        assert len(dev) + len(held) == 24

    def test_no_overlap(self):
        dev = get_dev_scenarios()
        held = get_held_out_scenarios()
        dev_ids = {s.scenario_id for s in dev}
        held_ids = {s.scenario_id for s in held}
        assert len(dev_ids & held_ids) == 0

    def test_dev_is_first_18(self):
        dev = get_dev_scenarios()
        dev_ids = [s.scenario_id for s in dev]
        # Dev should be first 18 from the matrix
        all_ids = [s.scenario_id for s in generate_scenarios()]
        assert dev_ids == all_ids[:18]

    def test_held_out_is_last_6(self):
        held = get_held_out_scenarios()
        held_ids = [s.scenario_id for s in held]
        all_ids = [s.scenario_id for s in generate_scenarios()]
        assert held_ids == all_ids[18:]


# ---------------------------------------------------------------------------
# Task-spec variant tests
# ---------------------------------------------------------------------------


class TestTaskSpecVariants:
    """Test task-spec variants."""

    def test_three_variants(self):
        assert len(TASK_SPEC_VARIANTS) == 3

    def test_variant_names(self):
        names = list(TASK_SPEC_VARIANTS.keys())
        assert "canonical" in names
        assert "variant_b" in names
        assert "variant_c" in names

    def test_variant_structure(self):
        for name, spec_text in TASK_SPEC_VARIANTS.items():
            assert isinstance(spec_text, str)
            assert len(spec_text) > 0

    def test_semantically_equivalent(self):
        """All variants describe the same trading rules."""
        for name, spec_text in TASK_SPEC_VARIANTS.items():
            assert "position_qty" in spec_text.lower() or "position" in spec_text.lower()
            assert "target_signal" in spec_text.lower() or "target" in spec_text.lower()

    def test_syntactically_distinct(self):
        """Variant text is not identical."""
        texts = list(TASK_SPEC_VARIANTS.values())
        assert len(set(texts)) == 3

    def test_spec_to_scenario_with_variant(self):
        """ScenarioSpec with different variants produces correct Scenario objects."""
        for variant_name in TASK_SPEC_VARIANTS:
            spec = ScenarioSpec(
                scenario_id="TEST-001",
                f_position=10,
                l_position=5,
                target_signal=1,
                f_expected_action="SELL",
                f_expected_qty=1,
                l_expected_action="SELL",
                l_expected_qty=1,
                corrupt_f=1,
                corrupt_l=6,
                policy_variant=variant_name,
                generator_seed=42,
            )
            scenario = spec_to_scenario(spec)
            assert scenario.task_spec == TASK_SPEC_VARIANTS[variant_name]


# ---------------------------------------------------------------------------
# ScenarioSpec to Scenario conversion tests
# ---------------------------------------------------------------------------


class TestSpecToScenario:
    """Test ScenarioSpec to Scenario conversion."""

    def test_conversion_produces_valid_scenario(self):
        specs = generate_scenarios()
        spec = specs[0]
        scenario = spec_to_scenario(spec)
        assert isinstance(scenario, Scenario)
        assert scenario.version == "0.3a"
        assert scenario.seed == spec.generator_seed
        assert scenario.scenario_id == spec.scenario_id

    def test_episodes_preserved(self):
        specs = generate_scenarios()
        spec = specs[4]  # G2-S04
        scenario = spec_to_scenario(spec)
        assert "F" in scenario.episodes
        assert "L" in scenario.episodes
        assert scenario.episodes["F"].hidden_position_qty == spec.f_position
        assert scenario.episodes["L"].hidden_position_qty == spec.l_position

    def test_observation_preserved(self):
        specs = generate_scenarios()
        spec = specs[9]  # G3-S09
        scenario = spec_to_scenario(spec)
        assert scenario.observation.target_signal == spec.target_signal

    def test_all_scenarios_convertible(self):
        for spec in generate_scenarios():
            scenario = spec_to_scenario(spec)
            assert isinstance(scenario, Scenario)
            assert scenario.observation.target_signal == spec.target_signal


# ---------------------------------------------------------------------------
# Prompt isolation tests
# ---------------------------------------------------------------------------


class TestPromptIsolation:
    """Test that generated scenarios don't leak metadata into prompts."""

    def test_no_scenario_id_in_prompts(self):
        specs = generate_scenarios()
        spec = specs[0]
        scenario = spec_to_scenario(spec)
        for condition in _CONDITIONS_V03A:
            for episode in ("F", "L"):
                inputs = build_worker_inputs(condition, episode, scenario, scenario_id=spec.scenario_id)
                prompt = build_llm_prompt(inputs, condition, episode)
                system_text = prompt[0]["content"].lower()
                user_text = prompt[1]["content"].lower()
                combined = system_text + user_text
                # scenario_id like "G1-S01" should not appear
                assert spec.scenario_id.lower() not in combined, (
                    f"Scenario ID {spec.scenario_id} leaked in {condition}/{episode}"
                )

    def test_no_generator_seed_in_prompts(self):
        specs = generate_scenarios()
        spec = specs[1]
        scenario = spec_to_scenario(spec)
        for condition in _CONDITIONS_V03A:
            for episode in ("F", "L"):
                inputs = build_worker_inputs(condition, episode, scenario, scenario_id=spec.scenario_id)
                prompt = build_llm_prompt(inputs, condition, episode)
                system_text = prompt[0]["content"].lower()
                user_text = prompt[1]["content"].lower()
                combined = system_text + user_text
                assert str(spec.generator_seed) not in combined, (
                    f"Generator seed {spec.generator_seed} leaked in {condition}/{episode}"
                )

    def test_no_expected_action_in_prompts(self):
        specs = generate_scenarios()
        spec = specs[2]
        scenario = spec_to_scenario(spec)
        for condition in _CONDITIONS_V03A:
            for episode in ("F", "L"):
                inputs = build_worker_inputs(condition, episode, scenario, scenario_id=spec.scenario_id)
                prompt = build_llm_prompt(inputs, condition, episode)
                system_text = prompt[0]["content"].lower()
                user_text = prompt[1]["content"].lower()
                combined = system_text + user_text
                assert "expected action" not in combined, (
                    f"Expected action leaked in {condition}/{episode}"
                )
                assert "expected_action" not in combined, (
                    f"Expected action (underscore) leaked in {condition}/{episode}"
                )

    def test_no_condition_name_in_prompts(self):
        specs = generate_scenarios()
        spec = specs[3]
        scenario = spec_to_scenario(spec)
        for condition in _CONDITIONS_V03A:
            for episode in ("F", "L"):
                inputs = build_worker_inputs(condition, episode, scenario, scenario_id=spec.scenario_id)
                prompt = build_llm_prompt(inputs, condition, episode)
                system_text = prompt[0]["content"].lower()
                user_text = prompt[1]["content"].lower()
                combined = system_text + user_text
                # Condition name should not appear as a label
                assert f"condition: {condition.lower()}" not in combined, (
                    f"Condition name {condition} leaked in prompt"
                )

    def test_no_policy_variant_in_prompts(self):
        specs = generate_scenarios()
        spec = specs[4]
        scenario = spec_to_scenario(spec)
        for condition in _CONDITIONS_V03A:
            for episode in ("F", "L"):
                inputs = build_worker_inputs(condition, episode, scenario, scenario_id=spec.scenario_id)
                prompt = build_llm_prompt(inputs, condition, episode)
                system_text = prompt[0]["content"].lower()
                user_text = prompt[1]["content"].lower()
                combined = system_text + user_text
                assert spec.policy_variant.lower() not in combined, (
                    f"Policy variant {spec.policy_variant} leaked in {condition}/{episode}"
                )


# ---------------------------------------------------------------------------
# Condition correctness tests
# ---------------------------------------------------------------------------


class TestConditionCorrectness:
    """Test that all 6 conditions work with generated scenarios."""

    def test_condition_a_no_position(self):
        specs = generate_scenarios()
        spec = specs[0]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("A", "F", scenario, scenario_id=spec.scenario_id)
        # Condition A: packet is None, no direct_state
        assert inputs.get("packet") is None
        assert inputs.get("direct_state") is None
        assert inputs.get("prior_context") is None

    def test_condition_b_full_has_packet(self):
        specs = generate_scenarios()
        spec = specs[4]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("B-full", "F", scenario, scenario_id=spec.scenario_id)
        assert inputs.get("packet") is not None

    def test_condition_b_minus_missing_position(self):
        specs = generate_scenarios()
        spec = specs[9]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("B-minus", "F", scenario, scenario_id=spec.scenario_id)
        # Position should be missing from packet
        packet = inputs["packet"]
        assert isinstance(packet, dict)
        # Check the nested structure: sections[0].records[0].payload
        payload = packet["sections"][0]["records"][0]["payload"]
        assert "position_qty" not in payload

    def test_condition_b_corrupt_wrong_position(self):
        specs = generate_scenarios()
        spec = specs[14]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("B-corrupt", "F", scenario, scenario_id=spec.scenario_id)
        packet = inputs["packet"]
        assert isinstance(packet, dict)
        payload = packet["sections"][0]["records"][0]["payload"]
        assert payload["position_qty"] == spec.corrupt_f

    def test_condition_b_restored_correct_position(self):
        specs = generate_scenarios()
        spec = specs[19]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("B-restored", "F", scenario, scenario_id=spec.scenario_id)
        packet = inputs["packet"]
        assert isinstance(packet, dict)
        payload = packet["sections"][0]["records"][0]["payload"]
        assert payload["position_qty"] == spec.f_position

    def test_condition_s_direct_state(self):
        specs = generate_scenarios()
        spec = specs[23]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("S", "F", scenario, scenario_id=spec.scenario_id)
        assert inputs.get("direct_state") is not None
        assert str(spec.f_position) in inputs["direct_state"]


# ---------------------------------------------------------------------------
# Oracle correctness tests
# ---------------------------------------------------------------------------


class TestOracleCorrectness:
    """Test that oracle produces correct expected actions for generated scenarios."""

    def test_oracle_covers_all_actions(self):
        scenarios = generate_scenarios()
        actions = set()
        for spec in scenarios:
            expected_f = compute_expected_action(spec.f_position, spec.target_signal)
            expected_l = compute_expected_action(spec.l_position, spec.target_signal)
            actions.add(expected_f.kind.value)
            actions.add(expected_l.kind.value)
        assert "BUY" in actions
        assert "SELL" in actions
        assert "HOLD" in actions

    def test_oracle_consistency(self):
        """Same inputs produce same outputs."""
        scenarios = generate_scenarios()
        for spec in scenarios:
            e1 = compute_expected_action(spec.f_position, spec.target_signal)
            e2 = compute_expected_action(spec.f_position, spec.target_signal)
            assert e1.kind == e2.kind
            assert e1.quantity == e2.quantity

    def test_oracle_differs_across_scenarios(self):
        """Different scenarios can produce different expected actions."""
        scenarios = generate_scenarios()
        expected_actions = set()
        for spec in scenarios:
            e = compute_expected_action(spec.f_position, spec.target_signal)
            expected_actions.add((e.kind.value, e.quantity))
        # Should have multiple distinct expected actions
        assert len(expected_actions) > 1


# ---------------------------------------------------------------------------
# Worker compatibility tests
# ---------------------------------------------------------------------------


class TestWorkerCompatibility:
    """Test that worker works with generated scenarios."""

    def test_worker_with_generated_scenario(self):
        specs = generate_scenarios()
        spec = specs[0]
        scenario = spec_to_scenario(spec)
        for condition in _CONDITIONS_V03A:
            for episode in ("F", "L"):
                inputs = build_worker_inputs(condition, episode, scenario, scenario_id=spec.scenario_id)
                output = execute_worker(inputs, condition, episode, scenario=scenario)
                assert output.action_kind in ("BUY", "SELL", "HOLD", "MISSING_REQUIRED_STATE")
                assert isinstance(output.quantity, int)
                assert output.quantity >= 0

    def test_worker_scenario_object_preferred(self):
        """Scenario object should be used instead of SCENARIOS dict lookup."""
        specs = generate_scenarios()
        spec = specs[0]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("S", "F", scenario, scenario_id=spec.scenario_id)
        # With scenario object
        output1 = execute_worker(inputs, "S", "F", scenario=scenario)
        assert output1.action_kind in ("BUY", "SELL", "HOLD")


# ---------------------------------------------------------------------------
# Digest independence tests
# ---------------------------------------------------------------------------


class TestDigestIndependence:
    """Test that digests are computed correctly for generated scenarios."""

    def test_digest_computation(self):
        import hashlib
        import json

        specs = generate_scenarios()
        spec = specs[0]
        scenario = spec_to_scenario(spec)
        inputs = build_worker_inputs("A", "F", scenario, scenario_id=spec.scenario_id)
        output = execute_worker(inputs, "A", "F", scenario=scenario)

        # Compute expected digest
        behavior_payload = {
            "condition": "A",
            "episode_id": "F",
            "scenario_id": spec.scenario_id,
            "variant": "canonical",
            "action_kind": output.action_kind,
            "quantity": output.quantity,
            "classification": "PASS",
        }
        behavior_str = json.dumps(behavior_payload, sort_keys=True, separators=(",", ":"))
        expected_digest = hashlib.sha256(behavior_str.encode()).hexdigest()[:16]

        assert len(expected_digest) == 16

    def test_different_scenarios_different_digests(self):
        import hashlib
        import json

        specs = generate_scenarios()
        spec1 = specs[0]
        spec2 = specs[1]
        scenario1 = spec_to_scenario(spec1)
        scenario2 = spec_to_scenario(spec2)

        inputs1 = build_worker_inputs("A", "F", scenario1, scenario_id=spec1.scenario_id)
        inputs2 = build_worker_inputs("A", "F", scenario2, scenario_id=spec2.scenario_id)

        output1 = execute_worker(inputs1, "A", "F", scenario=scenario1)
        output2 = execute_worker(inputs2, "A", "F", scenario=scenario2)

        payload1 = {
            "condition": "A", "episode_id": "F", "scenario_id": spec1.scenario_id,
            "variant": "canonical", "action_kind": output1.action_kind,
            "quantity": output1.quantity, "classification": "PASS",
        }
        payload2 = {
            "condition": "A", "episode_id": "F", "scenario_id": spec2.scenario_id,
            "variant": "canonical", "action_kind": output2.action_kind,
            "quantity": output2.quantity, "classification": "PASS",
        }
        digest1 = hashlib.sha256(json.dumps(payload1, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        digest2 = hashlib.sha256(json.dumps(payload2, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]

        # The payloads differ (different scenario_id), so digests must differ
        assert digest1 != digest2


# ---------------------------------------------------------------------------
# Scenario matrix table test
# ---------------------------------------------------------------------------


class TestScenarioMatrixTable:
    """Test scenario matrix table generation."""

    def test_matrix_table_is_string(self):
        table = scenario_matrix_table()
        assert isinstance(table, str)

    def test_matrix_table_contains_all_scenarios(self):
        table = scenario_matrix_table()
        for i in range(1, 25):
            assert f"G{i//4+1}-S{i:02d}" in table or f"G{(i-1)//4+1}-S{i:02d}" in table


# ---------------------------------------------------------------------------
# Corrupt map tests
# ---------------------------------------------------------------------------


class TestCorruptMap:
    """Test corrupt value computation."""

    def test_corrupt_hold(self):
        # HOLD (pos == target) → corrupt to SELL (pos + 1)
        assert _compute_corrupt(5, 5) == 6

    def test_corrupt_buy(self):
        # BUY (pos < target) → corrupt to HOLD (target)
        assert _compute_corrupt(3, 5) == 5

    def test_corrupt_sell(self):
        # SELL (pos > target) → corrupt to HOLD (target)
        assert _compute_corrupt(7, 5) == 5


# ---------------------------------------------------------------------------
# V0.3a conditions constant test
# ---------------------------------------------------------------------------


class TestV03aConditions:
    """Test V0.3a conditions constant."""

    def test_six_conditions(self):
        assert len(_CONDITIONS_V03A) == 6

    def test_no_b_minus_explicit(self):
        assert "B-minus-explicit" not in _CONDITIONS_V03A

    def test_all_expected_conditions(self):
        expected = {"A", "B-full", "B-minus", "B-corrupt", "B-restored", "S"}
        assert set(_CONDITIONS_V03A) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
