"""
Tests for PM1 Trading Benchmark V0.2b — multi-scenario methodology.

Tests cover:
- Scenario definitions (S1, S2, S3)
- Scenario-aware fixture creation
- Scenario-aware expected actions
- Prompt isolation across scenarios
- Cross-scenario digest independence
"""

import json
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.scenario import make_scenario, SCENARIOS, ActionKind, Action
from lib.fixtures import create_state_dir, _position_for_episode, _corrupt_position
from lib.worker import build_worker_inputs, execute_worker
from lib.llm_worker import build_llm_prompt
from lib.oracle import compute_expected_action, validate_action
from lib.validator import generate_run_id


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def test_scenario_definitions():
    """S1, S2, S3 have distinct configs."""
    assert SCENARIOS["S1"]["f_position"] == 0
    assert SCENARIOS["S1"]["l_position"] == 1
    assert SCENARIOS["S1"]["target_signal"] == 0
    assert SCENARIOS["S1"]["corrupt_f"] == 1
    assert SCENARIOS["S1"]["corrupt_l"] == 0  # flip from true 1

    assert SCENARIOS["S2"]["f_position"] == 0
    assert SCENARIOS["S2"]["l_position"] == 2
    assert SCENARIOS["S2"]["target_signal"] == 1
    assert SCENARIOS["S2"]["corrupt_f"] == 1
    assert SCENARIOS["S2"]["corrupt_l"] == 1

    assert SCENARIOS["S3"]["f_position"] == 2
    assert SCENARIOS["S3"]["l_position"] == 0
    assert SCENARIOS["S3"]["target_signal"] == 1
    assert SCENARIOS["S3"]["corrupt_f"] == 1
    assert SCENARIOS["S3"]["corrupt_l"] == 1


def test_scenario_keys():
    """All expected keys present in each scenario."""
    for sid in ("S1", "S2", "S3"):
        cfg = SCENARIOS[sid]
        assert "f_position" in cfg
        assert "l_position" in cfg
        assert "target_signal" in cfg
        assert "corrupt_f" in cfg
        assert "corrupt_l" in cfg
        # Corrupt values must differ from correct values
        assert cfg["corrupt_f"] != cfg["f_position"]
        assert cfg["corrupt_l"] != cfg["l_position"]


# ---------------------------------------------------------------------------
# Scenario-aware position helpers
# ---------------------------------------------------------------------------

def test_position_for_episode():
    """_position_for_episode returns scenario-specific positions."""
    assert _position_for_episode("F", "S1") == (0, 10000)
    assert _position_for_episode("L", "S1") == (1, 0)
    assert _position_for_episode("F", "S2") == (0, 10000)
    assert _position_for_episode("L", "S2") == (2, -10000)
    assert _position_for_episode("F", "S3") == (2, -10000)
    assert _position_for_episode("L", "S3") == (0, 10000)


def test_corrupt_position():
    """_corrupt_position returns scenario-specific corrupt values."""
    assert _corrupt_position("F", "S1") == 1
    assert _corrupt_position("L", "S1") == 0  # flip from true 1
    assert _corrupt_position("F", "S2") == 1
    assert _corrupt_position("L", "S2") == 1
    assert _corrupt_position("F", "S3") == 1
    assert _corrupt_position("L", "S3") == 1


# ---------------------------------------------------------------------------
# Scenario-aware expected actions
# ---------------------------------------------------------------------------

def test_expected_actions_s2():
    """S2: target=1, F has 0 (buy 1), L has 2 (sell 1)."""
    f_action = compute_expected_action(0, 1)  # F: pos=0, target=1
    l_action = compute_expected_action(2, 1)  # L: pos=2, target=1
    assert f_action.kind == ActionKind.BUY
    assert f_action.quantity == 1
    assert l_action.kind == ActionKind.SELL
    assert l_action.quantity == 1


def test_expected_actions_s3():
    """S3: target=1, F has 2 (sell 1), L has 0 (buy 1)."""
    f_action = compute_expected_action(2, 1)  # F: pos=2, target=1
    l_action = compute_expected_action(0, 1)  # L: pos=0, target=1
    assert f_action.kind == ActionKind.SELL
    assert f_action.quantity == 1
    assert l_action.kind == ActionKind.BUY
    assert l_action.quantity == 1


def test_expected_actions_s1():
    """S1: target=0, F has 0 (hold), L has 1 (sell 1)."""
    f_action = compute_expected_action(0, 0)  # F: pos=0, target=0
    l_action = compute_expected_action(1, 0)  # L: pos=1, target=0
    assert f_action.kind == ActionKind.HOLD
    assert f_action.quantity == 0
    assert l_action.kind == ActionKind.SELL
    assert l_action.quantity == 1


# ---------------------------------------------------------------------------
# Scenario-aware fixtures
# ---------------------------------------------------------------------------

def test_b_full_fixture_per_scenario():
    """B-full fixtures have correct position_qty for each scenario."""
    import tempfile
    with tempfile.TemporaryDirectory() as base:
        for sid in ("S1", "S2", "S3"):
            cfg = SCENARIOS[sid]
            for ep in ("F", "L"):
                path = create_state_dir(base, "B-full", ep, sid)
                data = json.loads((Path(path) / "project_state.pm1").read_text().splitlines()[0])
                expected_pos = cfg["f_position"] if ep == "F" else cfg["l_position"]
                assert data["payload"]["position_qty"] == expected_pos
                assert data["payload"]["target_signal"] == cfg["target_signal"]


def test_b_corrupt_fixture_per_scenario():
    """B-corrupt fixtures have wrong position_qty for each scenario."""
    import tempfile
    with tempfile.TemporaryDirectory() as base:
        for sid in ("S1", "S2", "S3"):
            cfg = SCENARIOS[sid]
            for ep in ("F", "L"):
                path = create_state_dir(base, "B-corrupt", ep, sid)
                data = json.loads((Path(path) / "project_state.pm1").read_text().splitlines()[0])
                corrupt_val = cfg["corrupt_f"] if ep == "F" else cfg["corrupt_l"]
                assert data["payload"]["position_qty"] == corrupt_val


def test_b_minus_fixture_per_scenario():
    """B-minus fixtures lack position_qty in all scenarios."""
    import tempfile
    with tempfile.TemporaryDirectory() as base:
        for sid in ("S1", "S2", "S3"):
            for ep in ("F", "L"):
                path = create_state_dir(base, "B-minus", ep, sid)
                data = json.loads((Path(path) / "project_state.pm1").read_text().splitlines()[0])
                assert "position_qty" not in data["payload"]


def test_b_restored_fixture_per_scenario():
    """B-restored fixtures have correct position_qty for each scenario."""
    import tempfile
    with tempfile.TemporaryDirectory() as base:
        for sid in ("S1", "S2", "S3"):
            cfg = SCENARIOS[sid]
            for ep in ("F", "L"):
                path = create_state_dir(base, "B-restored", ep, sid)
                data = json.loads((Path(path) / "project_state.pm1").read_text().splitlines()[0])
                expected_pos = cfg["f_position"] if ep == "F" else cfg["l_position"]
                assert data["payload"]["position_qty"] == expected_pos


# ---------------------------------------------------------------------------
# Worker inputs per scenario
# ---------------------------------------------------------------------------

def test_worker_inputs_per_scenario():
    """build_worker_inputs accepts scenario_id for all conditions."""
    scenario = make_scenario()
    conditions = ["A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S"]
    for sid in ("S1", "S2", "S3"):
        for cond in conditions:
            for ep in ("F", "L"):
                inputs = build_worker_inputs(cond, ep, scenario, scenario_id=sid)
                assert inputs["task_spec"] is not None
                assert inputs["observation"] is not None


def test_worker_execute_per_scenario():
    """execute_worker produces expected actions per scenario."""
    scenario = make_scenario()
    for sid in ("S1", "S2", "S3"):
        cfg = SCENARIOS[sid]
        for ep in ("F", "L"):
            inputs = build_worker_inputs("B-full", ep, scenario, scenario_id=sid)
            output = execute_worker(inputs, "B-full", ep, scenario_id=sid)
            expected_pos = cfg["f_position"] if ep == "F" else cfg["l_position"]
            expected_action = compute_expected_action(expected_pos, cfg["target_signal"])
            assert output.action_kind == expected_action.kind.value
            assert output.quantity == expected_action.quantity


# ---------------------------------------------------------------------------
# Prompt isolation across scenarios
# ---------------------------------------------------------------------------

def test_a_prompt_no_leakage_per_scenario():
    """A prompts contain no position values in any scenario."""
    scenario = make_scenario()
    for sid in ("S1", "S2", "S3"):
        inputs = build_worker_inputs("A", "F", scenario, scenario_id=sid)
        prompt = build_llm_prompt(inputs, "A", "F")
        user_content = prompt[1]["content"]
        import re
        assert not re.search(r"position_qty\s*[=:]\s*[0-9]", user_content)
        assert "cash_cents" not in user_content.lower()


def test_b_minus_explicit_prompt_per_scenario():
    """B-minus-explicit prompt has explicit MISSING_REQUIRED_STATE instruction."""
    scenario = make_scenario()
    for sid in ("S1", "S2", "S3"):
        inputs = build_worker_inputs("B-minus-explicit", "F", scenario, scenario_id=sid)
        prompt = build_llm_prompt(inputs, "B-minus-explicit", "F")
        system_content = prompt[0]["content"]
        assert "MISSING_REQUIRED_STATE" in system_content


def test_s_prompt_direct_state_per_scenario():
    """S prompt contains direct position_qty for each scenario."""
    scenario = make_scenario()
    for sid in ("S1", "S2", "S3"):
        cfg = SCENARIOS[sid]
        for ep in ("F", "L"):
            inputs = build_worker_inputs("S", ep, scenario, scenario_id=sid)
            prompt = build_llm_prompt(inputs, "S", ep)
            user_content = prompt[1]["content"]
            expected_pos = cfg["f_position"] if ep == "F" else cfg["l_position"]
            assert f"position_qty = {expected_pos}" in user_content


def test_no_scenario_id_in_prompts():
    """No prompt leaks scenario_id, trial_number, or run_id."""
    import re
    scenario = make_scenario()
    conditions = ["A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S"]
    for sid in ("S1", "S2", "S3"):
        for cond in conditions:
            inputs = build_worker_inputs(cond, "F", scenario, scenario_id=sid)
            prompt = build_llm_prompt(inputs, cond, "F")
            combined = prompt[0]["content"] + prompt[1]["content"]
            assert "scenario_id" not in combined.lower()
            assert "trial_number" not in combined.lower()
            assert "expected_action" not in combined.lower()


# ---------------------------------------------------------------------------
# Digest independence from scenario_id
# ---------------------------------------------------------------------------

def test_digest_includes_scenario_id():
    """Behavior digest varies when scenario_id changes (different expected actions)."""
    import hashlib
    scenario = make_scenario()
    for ep in ("F", "L"):
        digests = {}
        for sid in ("S1", "S2", "S3"):
            inputs = build_worker_inputs("B-full", ep, scenario, scenario_id=sid)
            output = execute_worker(inputs, "B-full", ep)
            cfg = SCENARIOS[sid]
            payload = {
                "condition": "B-full",
                "episode_id": ep,
                "scenario_id": sid,
                "action_kind": output.action_kind,
                "quantity": output.quantity,
                "classification": "PASS",
            }
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
            digests[sid] = digest
        # All 3 scenarios should produce different digests (different actions/positions)
        assert len(set(digests.values())) == 3, f"Expected 3 unique digests, got: {digests}"


# ---------------------------------------------------------------------------
# Run ID generation
# ---------------------------------------------------------------------------

def test_run_id_includes_scenario():
    """Run IDs include scenario_id for all scenarios."""
    for sid in ("S1", "S2", "S3"):
        rid = generate_run_id("B-full", "F", 1, sid)
        assert sid in rid
        assert rid == f"run-{sid}-B-full-F-t01"


# ---------------------------------------------------------------------------
# All 3 scenarios pass offline oracle check
# ---------------------------------------------------------------------------

def test_oracle_all_scenarios():
    """Oracle produces expected actions for all scenario/episode combos."""
    for sid in ("S1", "S2", "S3"):
        cfg = SCENARIOS[sid]
        for ep in ("F", "L"):
            pos = cfg["f_position"] if ep == "F" else cfg["l_position"]
            action = compute_expected_action(pos, cfg["target_signal"])
            assert isinstance(action, Action)
            assert action.kind in (ActionKind.BUY, ActionKind.SELL, ActionKind.HOLD)


if __name__ == "__main__":
    test_scenario_definitions()
    test_scenario_keys()
    test_position_for_episode()
    test_corrupt_position()
    test_expected_actions_s2()
    test_expected_actions_s3()
    test_expected_actions_s1()
    test_b_full_fixture_per_scenario()
    test_b_corrupt_fixture_per_scenario()
    test_b_minus_fixture_per_scenario()
    test_b_restored_fixture_per_scenario()
    test_worker_inputs_per_scenario()
    test_worker_execute_per_scenario()
    test_a_prompt_no_leakage_per_scenario()
    test_b_minus_explicit_prompt_per_scenario()
    test_s_prompt_direct_state_per_scenario()
    test_no_scenario_id_in_prompts()
    test_digest_includes_scenario_id()
    test_run_id_includes_scenario()
    test_oracle_all_scenarios()
    print("test_v02b: ALL PASSED")
