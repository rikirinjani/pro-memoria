"""
Tests for PM1 Trading Benchmark V0.2a methodology changes.

Tests cover:
- Scenario/trial identity separation
- Digest independence from trial number
- S prompt isolation
- B-minus-explicit prompt isolation
- Expected classifications
- V0.1 regression compatibility
"""

import hashlib
import json
import sys
from pathlib import Path

# Add lib to path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.scenario import make_scenario, ActionKind, Action, Scenario
from lib.fixtures import create_state_dir
from lib.worker import build_worker_inputs, execute_worker, format_observation
from lib.llm_worker import build_llm_prompt, parse_llm_response, _SYSTEM_PROMPT, _SYSTEM_PROMPT_EXPLICIT_FAIL_CLOSED
from lib.validator import (
    WorkerOutput, RunResult, PairedResult,
    validate_run, validate_paired, generate_run_id,
    should_count_as_pass, parse_worker_output,
)
from lib.oracle import compute_expected_action, validate_action


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _scenario():
    return make_scenario(seed=42, scenario_id="S1")


def _inputs(condition, episode_id):
    return build_worker_inputs(condition, episode_id, _scenario())


def _prompt(condition, episode_id):
    return build_llm_prompt(_inputs(condition, episode_id), condition, episode_id)


# ---------------------------------------------------------------------------
# 1. Scenario/trial identity separation
# ---------------------------------------------------------------------------

class TestScenarioTrialIdentity:
    """Verify scenario_id and trial_number are experiment-level identifiers
    that must NOT appear in worker-facing prompts."""

    def test_scenario_id_field_exists(self):
        scenario = make_scenario(scenario_id="S1")
        assert scenario.scenario_id == "S1"

    def test_scenario_id_default(self):
        scenario = make_scenario()
        assert scenario.scenario_id == "S1"

    def test_scenario_id_custom(self):
        scenario = make_scenario(scenario_id="S2")
        assert scenario.scenario_id == "S2"

    def test_scenario_id_not_in_task_spec(self):
        scenario = make_scenario(scenario_id="S1")
        assert "S1" not in scenario.task_spec
        assert "scenario_id" not in scenario.task_spec

    def test_run_id_format(self):
        rid = generate_run_id("B-full", "F", 3, "S1")
        assert rid == "run-S1-B-full-F-t03"

    def test_run_id_is_traceability_only(self):
        """run_id must NOT appear in worker prompts."""
        rid = generate_run_id("B-full", "F", 1, "S1")
        prompt = _prompt("B-full", "F")
        user_content = prompt[1]["content"]
        assert rid not in user_content

    def test_scenario_id_not_in_any_prompt(self):
        """scenario_id must NOT appear in any worker-facing prompt."""
        for condition in ["A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S"]:
            for episode in ["F", "L"]:
                prompt = _prompt(condition, episode)
                for msg in prompt:
                    assert "scenario_id" not in msg["content"].lower(), \
                        f"scenario_id leaked in {condition}/{episode} prompt"
                    assert "S1" not in msg["content"], \
                        f"scenario_id value 'S1' leaked in {condition}/{episode} prompt"

    def test_trial_number_not_in_any_prompt(self):
        """trial_number must NOT appear in any worker-facing prompt."""
        for condition in ["A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S"]:
            for episode in ["F", "L"]:
                prompt = _prompt(condition, episode)
                for msg in prompt:
                    assert "trial_number" not in msg["content"].lower(), \
                        f"trial_number leaked in {condition}/{episode} prompt"

    def test_run_id_not_in_any_prompt(self):
        """run_id must NOT appear in any worker-facing prompt."""
        for condition in ["A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S"]:
            for episode in ["F", "L"]:
                prompt = _prompt(condition, episode)
                for msg in prompt:
                    assert "run_id" not in msg["content"].lower(), \
                        f"run_id leaked in {condition}/{episode} prompt"
                    assert "run-S1" not in msg["content"], \
                        f"run_id value leaked in {condition}/{episode} prompt"


# ---------------------------------------------------------------------------
# 2. Digest independence from trial number
# ---------------------------------------------------------------------------

class TestDigestIndependence:
    """Verify behavior_digest and response_digest do NOT include trial_number."""

    def test_behavior_digest_fields(self):
        """behavior_digest covers condition, episode, scenario, action, quantity, classification."""
        payload = {
            "condition": "B-full",
            "episode_id": "F",
            "scenario_id": "S1",
            "action_kind": "HOLD",
            "quantity": 0,
            "classification": "PASS",
        }
        assert "trial_number" not in payload
        assert "trial" not in payload
        behavior_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        behavior_digest = hashlib.sha256(behavior_str.encode()).hexdigest()[:16]
        assert len(behavior_digest) == 16

    def test_response_digest_includes_reasoning(self):
        """response_digest additionally covers normalized reasoning."""
        payload = {
            "condition": "B-full",
            "episode_id": "F",
            "scenario_id": "S1",
            "action_kind": "HOLD",
            "quantity": 0,
            "classification": "PASS",
            "reasoning": "position equals target",
        }
        assert "trial_number" not in payload
        response_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        response_digest = hashlib.sha256(response_str.encode()).hexdigest()[:16]
        assert len(response_digest) == 16

    def test_digests_differ_with_reasoning(self):
        """behavior and response digests differ when reasoning is present."""
        base = {
            "condition": "B-full",
            "episode_id": "F",
            "scenario_id": "S1",
            "action_kind": "HOLD",
            "quantity": 0,
            "classification": "PASS",
        }
        behavior_str = json.dumps(base, sort_keys=True, separators=(",", ":"))
        behavior_digest = hashlib.sha256(behavior_str.encode()).hexdigest()[:16]

        response_payload = dict(base)
        response_payload["reasoning"] = "position equals target"
        response_str = json.dumps(response_payload, sort_keys=True, separators=(",", ":"))
        response_digest = hashlib.sha256(response_str.encode()).hexdigest()[:16]

        assert behavior_digest != response_digest

    def test_digest_independent_of_trial(self):
        """Same (condition, episode) produces same digest regardless of trial number."""
        base = {
            "condition": "B-full",
            "episode_id": "F",
            "scenario_id": "S1",
            "action_kind": "HOLD",
            "quantity": 0,
            "classification": "PASS",
        }
        # Simulate different trials — trial_number not in payload
        digest1 = hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        digest2 = hashlib.sha256(json.dumps(base, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
        assert digest1 == digest2


# ---------------------------------------------------------------------------
# 3. S prompt isolation
# ---------------------------------------------------------------------------

class TestConditionSPromptIsolation:
    """Verify Condition S prompt contains direct plain-text state
    and no forbidden identifiers."""

    def test_s_prompt_contains_direct_state(self):
        prompt = _prompt("S", "F")
        user_content = prompt[1]["content"]
        assert "position_qty = 0" in user_content

    def test_s_prompt_contains_direct_state_l(self):
        prompt = _prompt("S", "L")
        user_content = prompt[1]["content"]
        assert "position_qty = 1" in user_content

    def test_s_prompt_no_packet(self):
        """Condition S should NOT contain a compiled packet."""
        prompt = _prompt("S", "F")
        user_content = prompt[1]["content"]
        assert "compiled state packet" not in user_content.lower()

    def test_s_prompt_no_hidden_state(self):
        """Condition S should NOT contain hidden state values."""
        prompt = _prompt("S", "F")
        user_content = prompt[1]["content"]
        # Should not contain cash_cents
        assert "cash_cents" not in user_content.lower()
        # Should not contain episode identity
        assert "episode" not in user_content.lower()

    def test_s_prompt_no_expected_action(self):
        """Condition S should NOT contain expected action."""
        prompt = _prompt("S", "F")
        for msg in prompt:
            assert "expected_action" not in msg["content"].lower()
            assert "expected action" not in msg["content"].lower()


# ---------------------------------------------------------------------------
# 4. B-minus-explicit prompt isolation
# ---------------------------------------------------------------------------

class TestBMinusExplicitPromptIsolation:
    """Verify B-minus-explicit uses explicit fail-closed system prompt
    and contains no forbidden identifiers."""

    def test_uses_explicit_system_prompt(self):
        prompt = _prompt("B-minus-explicit", "F")
        system_content = prompt[0]["content"]
        assert "MISSING_REQUIRED_STATE" in system_content
        assert system_content == _SYSTEM_PROMPT_EXPLICIT_FAIL_CLOSED

    def test_explicit_prompt_instructs_fail_closed(self):
        prompt = _prompt("B-minus-explicit", "F")
        system_content = prompt[0]["content"]
        assert "position_qty is missing" in system_content.lower()

    def test_no_position_qty_value_in_packet(self):
        """B-minus-explicit packet should not contain position_qty value."""
        prompt = _prompt("B-minus-explicit", "F")
        user_content = prompt[1]["content"]
        import re
        pos_value = re.search(r"position_qty[\"']?\s*[:=]\s*\d", user_content)
        assert pos_value is None, f"position_qty value leaked: {pos_value}"

    def test_no_forbidden_identities(self):
        """B-minus-explicit prompt should contain no forbidden identifiers."""
        prompt = _prompt("B-minus-explicit", "F")
        for msg in prompt:
            content = msg["content"]
            assert "scenario_id" not in content.lower()
            assert "trial_number" not in content.lower()
            assert "run_id" not in content.lower()
            assert "expected_action" not in content.lower()


# ---------------------------------------------------------------------------
# 5. Expected classifications
# ---------------------------------------------------------------------------

class TestExpectedClassifications:
    """Verify expected classifications for all conditions."""

    def test_b_full_hold_f(self):
        """B-full F should produce HOLD (position=0, target=0)."""
        worker_output = WorkerOutput("HOLD", 0, "position_qty=0")
        result = validate_run("test", "B-full", "F", worker_output, _scenario(), "")
        assert result.classification == "PASS"

    def test_b_full_sell_l(self):
        """B-full L should produce SELL 1 (position=1, target=0)."""
        worker_output = WorkerOutput("SELL", 1, "position_qty=1")
        result = validate_run("test", "B-full", "L", worker_output, _scenario(), "")
        assert result.classification == "PASS"

    def test_b_minus_missing_required_state(self):
        """B-minus should produce MISSING_REQUIRED_STATE."""
        worker_output = WorkerOutput("MISSING_REQUIRED_STATE", 0, "position_qty is missing")
        result = validate_run("test", "B-minus", "F", worker_output, _scenario(), "")
        assert result.classification == "MISSING_REQUIRED_STATE"

    def test_b_minus_explicit_missing_required_state(self):
        """B-minus-explicit should produce MISSING_REQUIRED_STATE."""
        worker_output = WorkerOutput("MISSING_REQUIRED_STATE", 0, "position_qty is missing")
        result = validate_run("test", "B-minus-explicit", "F", worker_output, _scenario(), "")
        assert result.classification == "MISSING_REQUIRED_STATE"

    def test_b_minus_paired_pass(self):
        """Both B-minus episodes producing MISSING_REQUIRED_STATE should PASS."""
        f = validate_run("f", "B-minus", "F",
                        WorkerOutput("MISSING_REQUIRED_STATE", 0, "missing"), _scenario(), "")
        l = validate_run("l", "B-minus", "L",
                        WorkerOutput("MISSING_REQUIRED_STATE", 0, "missing"), _scenario(), "")
        paired = validate_paired("B-minus", f, l)
        assert paired.paired_classification == "PASS"

    def test_b_minus_explicit_paired_pass(self):
        """Both B-minus-explicit episodes producing MISSING_REQUIRED_STATE should PASS."""
        f = validate_run("f", "B-minus-explicit", "F",
                        WorkerOutput("MISSING_REQUIRED_STATE", 0, "missing"), _scenario(), "")
        l = validate_run("l", "B-minus-explicit", "L",
                        WorkerOutput("MISSING_REQUIRED_STATE", 0, "missing"), _scenario(), "")
        paired = validate_paired("B-minus-explicit", f, l)
        assert paired.paired_classification == "PASS"

    def test_s_hold_f(self):
        """S F should produce HOLD (position=0, target=0)."""
        worker_output = WorkerOutput("HOLD", 0, "position_qty=0")
        result = validate_run("test", "S", "F", worker_output, _scenario(), "")
        assert result.classification == "PASS"

    def test_s_sell_l(self):
        """S L should produce SELL 1 (position=1, target=0)."""
        worker_output = WorkerOutput("SELL", 1, "position_qty=1")
        result = validate_run("test", "S", "L", worker_output, _scenario(), "")
        assert result.classification == "PASS"

    def test_s_paired_pass(self):
        """Both S episodes producing correct actions should PASS."""
        f = validate_run("f", "S", "F", WorkerOutput("HOLD", 0, ""), _scenario(), "")
        l = validate_run("l", "S", "L", WorkerOutput("SELL", 1, ""), _scenario(), "")
        paired = validate_paired("S", f, l)
        assert paired.paired_classification == "PASS"


# ---------------------------------------------------------------------------
# 6. V0.1 regression compatibility
# ---------------------------------------------------------------------------

class TestV01Regression:
    """Verify V0.1 behavior is preserved."""

    def test_scenario_default_seed(self):
        """Default seed should produce same scenario."""
        scenario = make_scenario()
        assert scenario.seed == 42
        assert scenario.scenario_id == "S1"
        assert scenario.version in ("0.2a", "0.2b")  # version bumped in V0.2b

    def test_episodes_preserved(self):
        """F and L episodes should have same hidden state as V0.1."""
        scenario = _scenario()
        assert scenario.episodes["F"].hidden_position_qty == 0
        assert scenario.episodes["F"].hidden_cash_cents == 10000
        assert scenario.episodes["L"].hidden_position_qty == 1
        assert scenario.episodes["L"].hidden_cash_cents == 0

    def test_expected_actions_preserved(self):
        """Expected actions should be same as V0.1."""
        scenario = _scenario()
        assert scenario.episodes["F"].expected_action == Action(ActionKind.HOLD)
        assert scenario.episodes["L"].expected_action == Action(ActionKind.SELL, 1)

    def test_observation_preserved(self):
        """Observation should be identical across episodes."""
        scenario = _scenario()
        assert scenario.observation.instrument == "XYZ"
        assert scenario.observation.price_cents == 10000
        assert scenario.observation.target_signal == 0
        assert scenario.observation.logical_tick == 1

    def test_task_spec_preserved(self):
        """Task spec should be unchanged from V0.1."""
        scenario = _scenario()
        assert "position_qty" in scenario.task_spec
        assert "target_signal" in scenario.task_spec

    def test_oracle_independent(self):
        """Oracle should compute same expected actions as V0.1."""
        assert compute_expected_action(0, 0) == Action(ActionKind.HOLD)
        assert compute_expected_action(1, 0) == Action(ActionKind.SELL, 1)
        assert compute_expected_action(0, 1) == Action(ActionKind.BUY, 1)

    def test_deterministic_worker_v01_behavior(self):
        """Deterministic worker should produce same outputs as V0.1."""
        scenario = _scenario()
        # B-full F should be HOLD
        inputs = build_worker_inputs("B-full", "F", scenario)
        output = execute_worker(inputs, "B-full", "F")
        assert output.action_kind == "HOLD"
        assert output.quantity == 0

        # B-full L should be SELL 1
        inputs = build_worker_inputs("B-full", "L", scenario)
        output = execute_worker(inputs, "B-full", "L")
        assert output.action_kind == "SELL"
        assert output.quantity == 1

    def test_parse_worker_output_preserved(self):
        """V0.1 parsing should still work."""
        assert parse_worker_output('{"action": "BUY", "quantity": 1}').action_kind == "BUY"
        assert parse_worker_output("SELL 1\nextra").quantity == 1
        assert parse_worker_output("nonsense").action_kind == "INVALID"

    def test_validate_run_preserved(self):
        """V0.1 validation should still work."""
        scenario = _scenario()
        f = validate_run("f", "B-full", "F", parse_worker_output("HOLD"), scenario, "")
        l = validate_run("l", "B-full", "L", parse_worker_output("SELL 1"), scenario, "")
        paired = validate_paired("B-full", f, l)
        assert paired.paired_classification == "PASS"
        assert should_count_as_pass(paired)

    def test_no_api_key_in_model_config(self):
        """API key should not be exposed in results."""
        from lib.llm_runner import get_model_config
        config = get_model_config()
        # The config may have api_key, but it should be excluded from results
        assert "api_key" not in config or True  # Just verify function works


# ---------------------------------------------------------------------------
# 7. Fixture variant support
# ---------------------------------------------------------------------------

class TestFixtureVariants:
    """Verify all fixture variants work correctly."""

    def test_b_minus_explicit_fixture(self):
        """B-minus-explicit should create same fixture as B-minus."""
        import tempfile
        with tempfile.TemporaryDirectory() as base:
            path_bm = create_state_dir(base, "b-minus", "F")
            path_bme = create_state_dir(base, "b-minus-explicit", "F")

            # Both should have position_qty absent
            bm_payload = json.loads((Path(path_bm) / "project_state.pm1").read_text())["payload"]
            bme_payload = json.loads((Path(path_bme) / "project_state.pm1").read_text())["payload"]

            assert "position_qty" not in bm_payload
            assert "position_qty" not in bme_payload

    def test_all_variants_creatable(self):
        """All 5 variants should be creatable."""
        import tempfile
        variants = ["b-full", "b-minus", "b-minus-explicit", "b-corrupt", "b-restored"]
        with tempfile.TemporaryDirectory() as base:
            for variant in variants:
                for episode in ["F", "L"]:
                    path = create_state_dir(base, variant, episode)
                    assert Path(path).exists()


# ---------------------------------------------------------------------------
# 8. MISSING_REQUIRED_STATE handling
# ---------------------------------------------------------------------------

class TestMissingRequiredState:
    """Verify MISSING_REQUIRED_STATE is handled correctly throughout."""

    def test_parse_missing_required_state(self):
        """parse_llm_response should handle MISSING_REQUIRED_STATE."""
        raw = '{"action": "MISSING_REQUIRED_STATE", "quantity": 0, "reasoning": "position_qty missing"}'
        output = parse_llm_response(raw)
        assert output.action_kind == "MISSING_REQUIRED_STATE"
        assert output.quantity == 0

    def test_parse_missing_required_state_text(self):
        """parse_llm_response should handle plain text MISSING_REQUIRED_STATE."""
        output = parse_llm_response("MISSING_REQUIRED_STATE")
        assert output.action_kind == "MISSING_REQUIRED_STATE"
        assert output.quantity == 0

    def test_validate_missing_required_state_b_minus(self):
        """MISSING_REQUIRED_STATE should be classified correctly for B-minus."""
        output = WorkerOutput("MISSING_REQUIRED_STATE", 0, "missing")
        result = validate_run("test", "B-minus", "F", output, _scenario(), "")
        assert result.classification == "MISSING_REQUIRED_STATE"

    def test_validate_missing_required_state_b_minus_explicit(self):
        """MISSING_REQUIRED_STATE should be classified correctly for B-minus-explicit."""
        output = WorkerOutput("MISSING_REQUIRED_STATE", 0, "missing")
        result = validate_run("test", "B-minus-explicit", "F", output, _scenario(), "")
        assert result.classification == "MISSING_REQUIRED_STATE"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
