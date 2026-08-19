"""
PM1 Trading Benchmark v0.1-LLM / v0.2a / v0.2b / v0.3a — Experiment Runner.

V0.1-LLM: Runs 50 LLM executions across 5 seeds × 2 episodes × 5 conditions.
V0.2a: Runs 70 LLM executions across 1 scenario × 2 episodes × 7 conditions × 5 trials.
V0.2b: Runs 210 LLM executions across 3 scenarios × 2 episodes × 7 conditions × 5 trials.
V0.3a: Runs 1080 LLM executions across 24 scenarios × 2 episodes × 6 conditions × 3 variants × 1 trial
       (dev set = 18 scenarios, held-out set = 6 scenarios, tested separately).

Conditions (V0.2b): A, B-full, B-minus, B-minus-explicit, B-corrupt, B-restored, S.
Conditions (V0.3a): A, B-full, B-minus, B-corrupt, B-restored, S (no B-minus-explicit).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from the project root.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.scenario import Scenario, make_scenario, expected_result_matrix
from lib.fixtures import create_state_dir
from lib.worker import build_worker_inputs
from lib.llm_worker import execute_llm_worker, build_llm_prompt
from lib.validator import (
    WorkerOutput,
    RunResult,
    PairedResult,
    validate_run,
    validate_paired,
    generate_run_id,
)
from lib.scenario_generator import (
    generate_scenarios,
    get_dev_scenarios,
    get_held_out_scenarios,
    TASK_SPEC_VARIANTS,
    scenario_matrix_table,
)

__all__ = [
    "get_model_config",
    "perform_isolation_audit",
    "run_single_llm_experiment",
    "run_all_llm_experiments",
    "run_v03a_experiments",
    "generate_llm_report",
    "verify_llm_acceptance_criteria",
]


# ---------------------------------------------------------------------------
# V0.3a scenario helper
# ---------------------------------------------------------------------------


def scenario_spec_to_scenario(spec) -> Scenario:
    """Convert a ScenarioSpec from scenario_generator to a Scenario dataclass.

    This bridges the generated scenario format (ScenarioSpec) to the
    existing Scenario dataclass used by fixtures, worker, and oracle.
    Accepts both ScenarioSpec objects and dicts (from vars(spec)).
    """
    from dataclasses import replace
    from lib.scenario_generator import ScenarioSpec, spec_to_scenario
    # If spec is a dict (from vars()), reconstruct a ScenarioSpec
    if isinstance(spec, dict):
        spec = ScenarioSpec(**spec)
    scenario = spec_to_scenario(spec)
    # Set policy_variant (spec_to_scenario uses the default "canonical")
    return replace(scenario, policy_variant=spec.policy_variant)

# ---------------------------------------------------------------------------
# Run plan
# ---------------------------------------------------------------------------

_SEEDS = [42, 123, 456, 789, 101112]
_EPISODES = ["F", "L"]
_CONDITIONS = ["A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S"]
_CONDITIONS_V03A = ["A", "B-full", "B-minus", "B-corrupt", "B-restored", "S"]  # No B-minus-explicit
_SCENARIOS = ["S1", "S2", "S3"]
# V0.1-LLM: 5 seeds × 2 episodes × 5 conditions = 50
# V0.2a: 1 scenario × 2 episodes × 7 conditions × 5 trials = 70
# V0.2b: 3 scenarios × 2 episodes × 7 conditions × 5 trials = 210
# V0.3a: 24 scenarios × 2 episodes × 6 conditions × 3 variants × 1 trial = 864
#        Dev set: 18 scenarios = 648, Held-out: 6 scenarios = 216

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------


def _read_opencode_config() -> dict[str, str]:
    """Read provider credentials from the OpenCode config file as fallback.

    Returns {base_url, api_key} or empty strings if not found.
    Does NOT print or persist the API key.
    """
    # First try the pre-extracted credentials file.
    creds_path = Path(__file__).parent.parent / ".llm_creds.json"
    if creds_path.exists():
        try:
            data = json.loads(creds_path.read_text(encoding="utf-8"))
            base_url = data.get("base_url", "")
            api_key = data.get("api_key", "")
            if base_url and api_key:
                return {"base_url": base_url, "api_key": api_key}
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: parse the jsonc config file directly.
    config_path = Path.home() / ".config" / "opencode" / "opencode.jsonc"
    if not config_path.exists():
        return {"base_url": "", "api_key": ""}

    try:
        import re as _re
        raw = config_path.read_text(encoding="utf-8")
        # Extract opencode-go provider block via targeted regex.
        go_start = raw.find('"opencode-go"')
        if go_start != -1:
            go_section = raw[go_start:go_start + 500]
            base_match = _re.search(r'"baseURL"\s*:\s*"([^"]+)"', go_section)
            key_match = _re.search(r'"apiKey"\s*:\s*"([^"]+)"', go_section)
            if base_match and key_match:
                return {"base_url": base_match.group(1), "api_key": key_match.group(1)}
    except OSError:
        pass

    return {"base_url": "", "api_key": ""}


def get_model_config() -> dict[str, Any]:
    """Read LLM configuration from environment variables, falling back to OpenCode config.

    Returns a dict with keys: base_url, api_key, model, temperature,
    max_tokens, max_retries.  Does NOT print or persist the API key.
    """
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    # Read model from env var first; fall back to credential file; then default.
    model = os.environ.get("PM1_LLM_MODEL", "")

    # Fallback: read from OpenCode config / .llm_creds.json file.
    if not base_url or not api_key:
        fallback = _read_opencode_config()
        if not base_url:
            base_url = fallback["base_url"]
        if not api_key:
            api_key = fallback["api_key"]

    # If model not set via env, try reading from .llm_creds.json.
    if not model:
        creds_path = Path(__file__).parent.parent / ".llm_creds.json"
        if creds_path.exists():
            try:
                creds_data = json.loads(creds_path.read_text(encoding="utf-8"))
                model = creds_data.get("model", "")
            except (json.JSONDecodeError, OSError):
                pass
    if not model:
        model = "deepseek-v4-flash"

    temperature = float(os.environ.get("PM1_LLM_TEMPERATURE", "0.0"))
    max_tokens = int(os.environ.get("PM1_LLM_MAX_TOKENS", "2048"))
    max_retries = int(os.environ.get("PM1_LLM_MAX_RETRIES", "3"))

    if not base_url or not api_key:
        print(
            "[llm_runner] WARNING: No API credentials found in env vars or OpenCode config.",
            file=sys.stderr,
        )

    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "max_retries": max_retries,
    }


# ---------------------------------------------------------------------------
# Isolation audit
# ---------------------------------------------------------------------------


def perform_isolation_audit(model_config: dict[str, Any]) -> dict[str, Any]:
    """Verify prompt isolation before running the experiment.

    V0.2b: Audits all 3 scenarios (S1, S2, S3).

    Tests per scenario:
    1. A prompt contains no hidden position VALUE
    2. B-full prompt contains the compiled packet
    3. B-minus prompt's packet lacks position_qty value
    4. B-minus-explicit prompt uses explicit fail-closed system prompt
    5. B-corrupt prompt's packet has wrong position_qty for the scenario
    6. B-restored prompt's packet has correct position_qty
    7. Condition S prompt contains direct plain-text state
    8. No scenario_id, trial_number, run_id, or expected action in any prompt
    9. No module-level mutable experiment state leaks between calls
    10. Each call gets a fresh prompt (no shared state)
    """
    from .scenario import SCENARIOS
    scenario = make_scenario()
    tests: list[dict[str, Any]] = []
    prompt_samples: dict[str, str] = {}

    # For each scenario, run the basic isolation tests.
    for scenario_id in _SCENARIOS:
        cfg = SCENARIOS[scenario_id]

        # --- Test 1: A prompt isolation (no hidden position VALUE) ---
        inputs_a_f = build_worker_inputs("A", "F", scenario, scenario_id=scenario_id)
        prompt_a = build_llm_prompt(inputs_a_f, "A", "F")
        user_a = prompt_a[1]["content"]
        a_pos_val = re.search(r"position_qty\s*[=:]\s*[0-9]", user_a)
        a_cash = "cash_cents" in user_a.lower()
        a_episode = "episode" in user_a.lower()
        violations_a = []
        if a_pos_val:
            violations_a.append(f"position_qty value: {a_pos_val.group()}")
        if a_cash:
            violations_a.append("cash_cents")
        if a_episode:
            violations_a.append("episode")
        test1_pass = len(violations_a) == 0
        tests.append({
            "name": f"[{scenario_id}] A prompt contains no hidden state values",
            "passed": test1_pass,
            "detail": f"violations: {violations_a}" if violations_a else "clean — field name only, no values",
        })
        prompt_samples[f"{scenario_id}/A"] = user_a[:500]

        # --- Test 2: B-full prompt contains compiled packet ---
        inputs_bf_f = build_worker_inputs("B-full", "F", scenario, scenario_id=scenario_id)
        prompt_bf = build_llm_prompt(inputs_bf_f, "B-full", "F")
        user_bf = prompt_bf[1]["content"]
        has_packet = "compiled state packet" in user_bf.lower() or "position_qty" in user_bf
        tests.append({
            "name": f"[{scenario_id}] B-full prompt contains compiled packet",
            "passed": has_packet,
            "detail": "packet section found" if has_packet else "packet section MISSING",
        })
        prompt_samples[f"{scenario_id}/B-full"] = user_bf[:500]

        # --- Test 3: B-minus prompt lacks position_qty in packet ---
        inputs_bm_f = build_worker_inputs("B-minus", "F", scenario, scenario_id=scenario_id)
        prompt_bm = build_llm_prompt(inputs_bm_f, "B-minus", "F")
        user_bm = prompt_bm[1]["content"]
        pos_value_pattern = re.search(r"position_qty[\"']?\s*[:=]\s*\d", user_bm)
        test3_pass = pos_value_pattern is None
        tests.append({
            "name": f"[{scenario_id}] B-minus prompt lacks position_qty value",
            "passed": test3_pass,
            "detail": "no position_qty value found" if test3_pass else "position_qty value leaked",
        })
        prompt_samples[f"{scenario_id}/B-minus"] = user_bm[:500]

        # --- Test 4: B-minus-explicit uses explicit fail-closed system prompt ---
        inputs_bme_f = build_worker_inputs("B-minus-explicit", "F", scenario, scenario_id=scenario_id)
        prompt_bme = build_llm_prompt(inputs_bme_f, "B-minus-explicit", "F")
        system_bme = prompt_bme[0]["content"]
        has_explicit_instruction = "MISSING_REQUIRED_STATE" in system_bme
        tests.append({
            "name": f"[{scenario_id}] B-minus-explicit uses explicit fail-closed system prompt",
            "passed": has_explicit_instruction,
            "detail": "MISSING_REQUIRED_STATE instruction found" if has_explicit_instruction else "explicit instruction MISSING",
        })
        prompt_samples[f"{scenario_id}/B-minus-explicit"] = prompt_bme[1]["content"][:500]

        # --- Test 5: B-corrupt prompt has wrong position_qty for scenario ---
        inputs_bc_f = build_worker_inputs("B-corrupt", "F", scenario, scenario_id=scenario_id)
        prompt_bc = build_llm_prompt(inputs_bc_f, "B-corrupt", "F")
        user_bc = prompt_bc[1]["content"]
        corrupt_val = cfg["corrupt_f"]
        has_corrupt = re.search(rf"position_qty[\"']?\s*[:=]\s*{corrupt_val}", user_bc)
        tests.append({
            "name": f"[{scenario_id}] B-corrupt F prompt has corrupted position_qty (should be {corrupt_val})",
            "passed": has_corrupt is not None,
            "detail": f"corrupt value {corrupt_val} found" if has_corrupt else f"corrupt value {corrupt_val} NOT found",
        })
        prompt_samples[f"{scenario_id}/B-corrupt"] = user_bc[:500]

        # --- Test 6: B-restored prompt has correct position_qty ---
        inputs_br_f = build_worker_inputs("B-restored", "F", scenario, scenario_id=scenario_id)
        prompt_br = build_llm_prompt(inputs_br_f, "B-restored", "F")
        user_br = prompt_br[1]["content"]
        correct_val = cfg["f_position"]
        has_correct = re.search(rf"position_qty[\"']?\s*[:=]\s*{correct_val}", user_br)
        tests.append({
            "name": f"[{scenario_id}] B-restored F prompt has correct position_qty (should be {correct_val})",
            "passed": has_correct is not None,
            "detail": f"correct value {correct_val} found" if has_correct else f"correct value {correct_val} NOT found",
        })
        prompt_samples[f"{scenario_id}/B-restored"] = user_br[:500]

        # --- Test 7: Condition S prompt contains direct plain-text state ---
        inputs_s_f = build_worker_inputs("S", "F", scenario, scenario_id=scenario_id)
        prompt_s = build_llm_prompt(inputs_s_f, "S", "F")
        user_s = prompt_s[1]["content"]
        expected_pos_s = cfg["f_position"]
        has_direct_state = f"position_qty = {expected_pos_s}" in user_s
        tests.append({
            "name": f"[{scenario_id}] Condition S F prompt contains direct plain-text state (position_qty = {expected_pos_s})",
            "passed": has_direct_state,
            "detail": "direct state found" if has_direct_state else "direct state MISSING",
        })
        prompt_samples[f"{scenario_id}/S"] = user_s[:500]

        # --- Test 8: No scenario_id, trial_number, run_id, or expected action in any prompt ---
        all_user = [user_a, user_bm, user_bc, user_br, user_s, user_bf]
        all_system = [prompt_a[0]["content"], prompt_bm[0]["content"], prompt_bme[0]["content"],
                      prompt_bc[0]["content"], prompt_br[0]["content"], prompt_s[0]["content"],
                      prompt_bf[0]["content"]]
        leaked_identities = []
        for i, (usr, sys_p) in enumerate(zip(all_user + [prompt_bme[1]["content"]], all_system)):
            combined = usr + sys_p
            if "scenario_id" in combined.lower():
                leaked_identities.append(f"scenario_id in prompt {i}")
            if "trial_number" in combined.lower():
                leaked_identities.append(f"trial_number in prompt {i}")
            if "run_id" in combined.lower() or "run-S1" in combined:
                leaked_identities.append(f"run_id in prompt {i}")
            if "expected_action" in combined.lower() or "expected action" in combined.lower():
                leaked_identities.append(f"expected action in prompt {i}")
        tests.append({
            "name": f"[{scenario_id}] No scenario_id, trial_number, run_id, or expected action in prompts",
            "passed": len(leaked_identities) == 0,
            "detail": "clean — no leaked identities" if not leaked_identities else f"leaked: {leaked_identities}",
        })

    # --- Test: No shared mutable prompt state (runs once, not per scenario) ---
    inputs_a_f = build_worker_inputs("A", "F", scenario, scenario_id="S1")
    p1 = build_llm_prompt(inputs_a_f, "A", "F")
    p2 = build_llm_prompt(inputs_a_f, "A", "F")
    independent = p1 is not p2
    tests.append({
        "name": "No shared mutable prompt state between calls",
        "passed": independent,
        "detail": "independent objects" if independent else "same object — shared state leak",
    })

    all_passed = all(t["passed"] for t in tests)
    return {
        "passed": all_passed,
        "tests": tests,
        "prompt_samples": prompt_samples,
    }


# ---------------------------------------------------------------------------
# Single experiment
# ---------------------------------------------------------------------------

import re  # noqa: E402 — needed for isolation audit regex


def run_single_llm_experiment(
    condition: str,
    episode_id: str,
    trial_number: int,
    scenario: Scenario,
    base_dir: str,
    model_config: dict[str, Any],
    scenario_id: str = "S1",
) -> RunResult:
    """Run one LLM experiment: build inputs, call LLM, validate.

    V0.2b: Uses scenario_id + trial_number for experiment-level identification.
    run_id is purely a traceability identifier.
    """
    run_id = generate_run_id(condition, episode_id, trial_number, scenario_id)

    # Build worker inputs (creates fixtures and invokes assembler as needed).
    inputs = build_worker_inputs(condition, episode_id, scenario, scenario_id=scenario_id)
    state_dir = inputs.get("state_dir", "")

    # Execute the LLM worker.
    worker_output = execute_llm_worker(inputs, condition, episode_id, model_config)

    # Validate against independent oracle.
    return validate_run(
        run_id=run_id,
        condition=condition,
        episode_id=episode_id,
        worker_output=worker_output,
        scenario=scenario,
        state_fixture_path=state_dir or "",
        assembled_packet_path=None,
        is_replay=False,
    )


# ---------------------------------------------------------------------------
# Full experiment
# ---------------------------------------------------------------------------


def run_all_llm_experiments(seed: int = 42) -> dict[str, Any]:
    """Run all V0.2b LLM experiments and return structured results.

    V0.2b: 3 scenarios × 2 episodes × 7 conditions × 5 trials = 210 executions.
    Uses scenario_id + trial_number for experiment-level identification.
    """
    model_config = get_model_config()
    scenario = make_scenario(seed)

    # Isolation audit (no API calls).
    isolation_audit = perform_isolation_audit(model_config)
    if not isolation_audit["passed"]:
        print("[llm_runner] ISOLATION AUDIT FAILED — aborting experiment.", file=sys.stderr)
        for t in isolation_audit["tests"]:
            if not t["passed"]:
                print(f"  FAIL: {t['name']}: {t['detail']}", file=sys.stderr)
        return {
            "all_runs": [],
            "paired_results": {},
            "run_digests": [],
            "trials": list(range(1, 6)),
            "model_config": {k: v for k, v in model_config.items() if k != "api_key"},
            "isolation_audit": isolation_audit,
            "scenario": scenario,
            "aborted": True,
            "abort_reason": "isolation audit failed",
        }

    print("[llm_runner] Isolation audit passed.", file=sys.stderr)

    all_runs: list[RunResult] = []
    paired_results: dict[str, PairedResult] = {}
    run_digests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="pm1-llm-benchmark-") as base_dir:
        for scenario_id in _SCENARIOS:
            for trial_number in range(1, 6):  # 5 trials
                for condition in _CONDITIONS:
                    for episode_id in _EPISODES:
                        try:
                            result = run_single_llm_experiment(
                                condition, episode_id, trial_number,
                                scenario, base_dir, model_config,
                                scenario_id=scenario_id,
                            )
                            all_runs.append(result)

                            # V0.2b: Compute behavior_digest and response_digest
                            # behavior_digest covers condition, episode, scenario, action, quantity, classification
                            behavior_payload = {
                                "condition": condition,
                                "episode_id": episode_id,
                                "scenario_id": scenario_id,
                                "action_kind": result.worker_output.action_kind,
                                "quantity": result.worker_output.quantity,
                                "classification": result.classification,
                            }
                            behavior_str = json.dumps(behavior_payload, sort_keys=True, separators=(",", ":"))
                            behavior_digest = hashlib.sha256(behavior_str.encode()).hexdigest()[:16]

                            # response_digest additionally covers normalized reasoning
                            reasoning = result.worker_output.reasoning.strip().lower()
                            response_payload = dict(behavior_payload)
                            response_payload["reasoning"] = reasoning
                            response_str = json.dumps(response_payload, sort_keys=True, separators=(",", ":"))
                            response_digest = hashlib.sha256(response_str.encode()).hexdigest()[:16]

                            run_digests.append({
                                "run_id": result.run_id,
                                "behavior_digest": behavior_digest,
                                "response_digest": response_digest,
                                "scenario_id": scenario_id,
                                "trial_number": trial_number,
                                "condition": condition,
                                "episode_id": episode_id,
                            })
                        except Exception as exc:
                            errors.append({
                                "scenario_id": scenario_id,
                                "trial_number": trial_number,
                                "condition": condition,
                                "episode_id": episode_id,
                                "error": str(exc),
                            })
                            print(
                                f"[llm_runner] ERROR {scenario_id} trial={trial_number} {condition}/{episode_id}: {exc}",
                                file=sys.stderr,
                            )

    # Pair F+L results for each condition across all trials and scenarios.
    for scenario_id in _SCENARIOS:
        for condition in _CONDITIONS:
            runs_f = [r for r in all_runs if r.condition == condition and r.episode_id == "F"
                      and f"run-{scenario_id}-{condition}-" in r.run_id]
            runs_l = [r for r in all_runs if r.condition == condition and r.episode_id == "L"
                      and f"run-{scenario_id}-{condition}-" in r.run_id]
            if runs_f and runs_l:
                # Use the first trial's results for the primary paired analysis.
                paired = validate_paired(condition, runs_f[0], runs_l[0])
                paired_results[f"{scenario_id}/{condition}"] = paired

    return {
        "all_runs": all_runs,
        "paired_results": paired_results,
        "run_digests": run_digests,
        "trials": list(range(1, 6)),
        "model_config": {k: v for k, v in model_config.items() if k != "api_key"},
        "isolation_audit": isolation_audit,
        "errors": errors,
        "scenario": scenario,
    }


# ---------------------------------------------------------------------------
# V0.3a experiment runner
# ---------------------------------------------------------------------------


def run_v03a_single_experiment(
    scenario_spec,
    condition: str,
    episode_id: str,
    variant: str,
    base_dir: str,
    model_config: dict[str, Any],
) -> RunResult:
    """Run one V0.3a LLM experiment: build inputs, call LLM, validate.

    V0.3a: Uses generated ScenarioSpec, task-spec variant, and scenario_id.
    """
    scenario = scenario_spec_to_scenario(scenario_spec)
    run_id = generate_run_id(condition, episode_id, 1, scenario_spec.scenario_id, variant)

    inputs = build_worker_inputs(condition, episode_id, scenario, scenario_id=scenario_spec.scenario_id)
    state_dir = inputs.get("state_dir", "")

    worker_output = execute_llm_worker(inputs, condition, episode_id, model_config)

    return validate_run(
        run_id=run_id,
        condition=condition,
        episode_id=episode_id,
        worker_output=worker_output,
        scenario=scenario,
        state_fixture_path=state_dir or "",
        assembled_packet_path=None,
        is_replay=False,
    )


def run_v03a_experiments(
    split: str = "dev",
    model_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run V0.3a experiments for a given split (dev or held-out).

    V0.3a: 24 scenarios × 2 episodes × 6 conditions × 3 variants × 1 trial.
    Dev set: first 18 scenarios (648 API calls).
    Held-out set: last 6 scenarios (216 API calls).

    Parameters
    ----------
    split : str
        "dev" or "held-out"
    model_config : dict, optional
        Model configuration. If None, reads from env/config.
    """
    if model_config is None:
        model_config = get_model_config()

    if split == "dev":
        scenario_specs = get_dev_scenarios()
    else:
        scenario_specs = get_held_out_scenarios()

    all_runs: list[RunResult] = []
    paired_results: dict[str, PairedResult] = {}
    run_digests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix=f"pm1-v03a-{split}-") as base_dir:
        for spec in scenario_specs:
            for variant in TASK_SPEC_VARIANTS:
                for condition in _CONDITIONS_V03A:
                    for episode_id in _EPISODES:
                        try:
                            result = run_v03a_single_experiment(
                                spec, condition, episode_id, variant,
                                base_dir, model_config,
                            )
                            all_runs.append(result)

                            # Compute digests
                            behavior_payload = {
                                "condition": condition,
                                "episode_id": episode_id,
                                "scenario_id": spec.scenario_id,
                                "variant": variant,
                                "action_kind": result.worker_output.action_kind,
                                "quantity": result.worker_output.quantity,
                                "classification": result.classification,
                            }
                            behavior_str = json.dumps(behavior_payload, sort_keys=True, separators=(",", ":"))
                            behavior_digest = hashlib.sha256(behavior_str.encode()).hexdigest()[:16]

                            reasoning = result.worker_output.reasoning.strip().lower()
                            response_payload = dict(behavior_payload)
                            response_payload["reasoning"] = reasoning
                            response_str = json.dumps(response_payload, sort_keys=True, separators=(",", ":"))
                            response_digest = hashlib.sha256(response_str.encode()).hexdigest()[:16]

                            run_digests.append({
                                "run_id": result.run_id,
                                "behavior_digest": behavior_digest,
                                "response_digest": response_digest,
                                "scenario_id": spec.scenario_id,
                                "variant": variant,
                                "condition": condition,
                                "episode_id": episode_id,
                            })
                        except Exception as exc:
                            errors.append({
                                "scenario_id": spec.scenario_id,
                                "variant": variant,
                                "condition": condition,
                                "episode_id": episode_id,
                                "error": str(exc),
                            })
                            print(
                                f"[llm_runner] ERROR {spec.scenario_id} {variant} {condition}/{episode_id}: {exc}",
                                file=sys.stderr,
                            )

    # Pair F+L results
    for spec in scenario_specs:
        for variant in TASK_SPEC_VARIANTS:
            for condition in _CONDITIONS_V03A:
                runs_f = [r for r in all_runs if r.condition == condition and r.episode_id == "F"
                          and spec.scenario_id in r.run_id and variant in r.run_id]
                runs_l = [r for r in all_runs if r.condition == condition and r.episode_id == "L"
                          and spec.scenario_id in r.run_id and variant in r.run_id]
                if runs_f and runs_l:
                    paired = validate_paired(condition, runs_f[0], runs_l[0])
                    paired_results[f"{spec.scenario_id}/{variant}/{condition}"] = paired

    return {
        "all_runs": all_runs,
        "paired_results": paired_results,
        "run_digests": run_digests,
        "model_config": {k: v for k, v in model_config.items() if k != "api_key"},
        "errors": errors,
        "split": split,
        "scenario_specs": [vars(s) for s in scenario_specs],
    }


def run_v03a_pilot(
    scenario_ids: list[str] | None = None,
    variants: list[str] | None = None,
    trials: int = 1,
    model_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a small V0.3a pilot experiment.

    Default: 2 scenarios × 2 episodes × 6 conditions × 1 variant × 1 trial = 24 calls.
    Covers HOLD, BUY, SELL actions and both canonical/variant_b policy variants.

    Parameters
    ----------
    scenario_ids : list[str], optional
        Which scenario IDs to run. Default: ["G1-S01", "G2-S04"].
    variants : list[str], optional
        Which task-spec variants to run. Default: ["canonical"].
    trials : int
        Number of trials per (scenario, variant, condition, episode). Default: 1.
    model_config : dict, optional
        Model configuration. If None, reads from env/config.
    """
    if model_config is None:
        model_config = get_model_config()

    # Import scenario specs
    from .scenario_generator import generate_scenarios
    all_specs = {s.scenario_id: s for s in generate_scenarios(seed=42)}

    if scenario_ids is None:
        scenario_ids = ["G1-S01", "G2-S04"]  # HOLD/SELL + BUY/HOLD
    if variants is None:
        variants = ["canonical"]

    scenario_specs = [all_specs[sid] for sid in scenario_ids if sid in all_specs]

    all_runs: list[RunResult] = []
    paired_results: dict[str, PairedResult] = {}
    run_digests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_calls = len(scenario_specs) * len(variants) * len(_CONDITIONS_V03A) * len(_EPISODES) * trials

    print(f"[llm_runner] V0.3a pilot: {len(scenario_specs)} scenarios × "
          f"{len(variants)} variants × {len(_CONDITIONS_V03A)} conditions × "
          f"{len(_EPISODES)} episodes × {trials} trials = {total_calls} API calls",
          file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="pm1-v03a-pilot-") as base_dir:
        for spec in scenario_specs:
            for variant in variants:
                for condition in _CONDITIONS_V03A:
                    for trial_num in range(1, trials + 1):
                        for episode_id in _EPISODES:
                            try:
                                scenario = scenario_spec_to_scenario(spec)
                                run_id = generate_run_id(
                                    condition, episode_id, trial_num,
                                    spec.scenario_id, variant,
                                )
                                inputs = build_worker_inputs(
                                    condition, episode_id, scenario,
                                    scenario_id=spec.scenario_id,
                                )
                                state_dir = inputs.get("state_dir", "")
                                worker_output = execute_llm_worker(
                                    inputs, condition, episode_id, model_config,
                                )
                                result = validate_run(
                                    run_id=run_id,
                                    condition=condition,
                                    episode_id=episode_id,
                                    worker_output=worker_output,
                                    scenario=scenario,
                                    state_fixture_path=state_dir or "",
                                    assembled_packet_path=None,
                                    is_replay=False,
                                )
                                all_runs.append(result)

                                # Compute digests
                                behavior_payload = {
                                    "condition": condition,
                                    "episode_id": episode_id,
                                    "scenario_id": spec.scenario_id,
                                    "variant": variant,
                                    "trial": trial_num,
                                    "action_kind": result.worker_output.action_kind,
                                    "quantity": result.worker_output.quantity,
                                    "classification": result.classification,
                                }
                                behavior_str = json.dumps(behavior_payload, sort_keys=True, separators=(",", ":"))
                                behavior_digest = hashlib.sha256(behavior_str.encode()).hexdigest()[:16]

                                reasoning = result.worker_output.reasoning.strip().lower()
                                response_payload = dict(behavior_payload)
                                response_payload["reasoning"] = reasoning
                                response_str = json.dumps(response_payload, sort_keys=True, separators=(",", ":"))
                                response_digest = hashlib.sha256(response_str.encode()).hexdigest()[:16]

                                run_digests.append({
                                    "run_id": result.run_id,
                                    "behavior_digest": behavior_digest,
                                    "response_digest": response_digest,
                                    "scenario_id": spec.scenario_id,
                                    "variant": variant,
                                    "trial": trial_num,
                                    "condition": condition,
                                    "episode_id": episode_id,
                                })
                            except Exception as exc:
                                errors.append({
                                    "scenario_id": spec.scenario_id,
                                    "variant": variant,
                                    "trial": trial_num,
                                    "condition": condition,
                                    "episode_id": episode_id,
                                    "error": str(exc),
                                })
                                print(
                                    f"[llm_runner] ERROR {spec.scenario_id} {variant} "
                                    f"trial={trial_num} {condition}/{episode_id}: {exc}",
                                    file=sys.stderr,
                                )

    # Pair F+L results
    for spec in scenario_specs:
        for variant in variants:
            for condition in _CONDITIONS_V03A:
                runs_f = [r for r in all_runs if r.condition == condition and r.episode_id == "F"
                          and spec.scenario_id in r.run_id and variant in r.run_id]
                runs_l = [r for r in all_runs if r.condition == condition and r.episode_id == "L"
                          and spec.scenario_id in r.run_id and variant in r.run_id]
                if runs_f and runs_l:
                    paired = validate_paired(condition, runs_f[0], runs_l[0])
                    paired_results[f"{spec.scenario_id}/{variant}/{condition}"] = paired

    return {
        "all_runs": all_runs,
        "paired_results": paired_results,
        "run_digests": run_digests,
        "model_config": {k: v for k, v in model_config.items() if k != "api_key"},
        "errors": errors,
        "scenario_specs": [vars(s) for s in scenario_specs],
        "variants": variants,
        "trials": trials,
    }


# ---------------------------------------------------------------------------
# Determinism tracking
# ---------------------------------------------------------------------------


def _check_cross_trial_consistency(run_digests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check whether the same (scenario, condition, episode) produces the same action across trials.

    V0.2b: Groups by (scenario_id, condition, episode_id).
    This is NOT a determinism guarantee for LLMs — it is a diagnostic.
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for d in run_digests:
        key = (d.get("scenario_id", "S1"), d["condition"], d["episode_id"])
        groups.setdefault(key, []).append(d)

    inconsistencies: list[dict[str, Any]] = []
    for key, group in sorted(groups.items()):
        digests = [g["behavior_digest"] for g in group]
        if len(set(digests)) > 1:
            inconsistencies.append({
                "scenario_id": key[0],
                "condition": key[1],
                "episode_id": key[2],
                "unique_digests": len(set(digests)),
                "total_runs": len(group),
                "note": "LLM outputs may vary across trials — this is a diagnostic, not a failure",
            })
    return inconsistencies


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_llm_report(results: dict[str, Any]) -> str:
    """Generate the V0.2b experiment report in markdown."""

    scenario = results["scenario"]
    all_runs = results["all_runs"]
    paired = results["paired_results"]
    digests = results["run_digests"]
    model_cfg = results["model_config"]
    audit = results["isolation_audit"]
    errors = results.get("errors", [])

    lines: list[str] = []
    w = lines.append

    w("# PM1 Trading Benchmark v0.2b — Experiment Report")
    w("")
    w("## Metadata")
    w("")
    w(f"- **Version:** v0.2b")
    w(f"- **Scenarios:** S1, S2, S3")
    w(f"- **Model:** {model_cfg.get('model', 'unknown')}")
    w(f"- **Provider:** OpenAI-compatible endpoint ({model_cfg.get('base_url', 'unknown')})")
    w(f"- **Temperature:** {model_cfg.get('temperature', 'unknown')}")
    w(f"- **Max tokens:** {model_cfg.get('max_tokens', 'unknown')}")
    w(f"- **Trials:** {results['trials']}")
    w(f"- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    w(f"- **Total planned calls:** {len(_SCENARIOS) * len(_EPISODES) * len(_CONDITIONS) * len(results['trials'])}")
    w(f"- **Total successful runs:** {len(all_runs)}")
    w(f"- **Total errors:** {len(errors)}")
    w(f"- **Conditions:** {', '.join(_CONDITIONS)}")
    w("")

    # --- Scenario definitions ---
    w("## Scenario Definitions")
    w("")
    w("| Scenario | F position | L position | target_signal | corrupt_f | corrupt_l |")
    w("|---|---|---|---|---|---|")
    from .scenario import SCENARIOS
    for sid in _SCENARIOS:
        cfg = SCENARIOS[sid]
        w(f"| {sid} | {cfg['f_position']} | {cfg['l_position']} | {cfg['target_signal']} | {cfg['corrupt_f']} | {cfg['corrupt_l']} |")
    w("")

    w("## Determinism Note")
    w("")
    w("**LLM outputs are NOT guaranteed deterministic**, even at temperature=0.0.")
    w("Cross-trial consistency is reported as a diagnostic, not a pass/fail criterion.")
    w("Replay determinism (identical inputs → identical outputs) depends on the provider")
    w("and model implementation and may not hold.")
    w("")

    # --- Isolation audit ---
    w("## Isolation Audit")
    w("")
    w(f"**Overall:** {'PASS' if audit['passed'] else 'FAIL'}")
    w("")
    for t in audit["tests"]:
        mark = "PASS" if t["passed"] else "FAIL"
        w(f"- [{mark}] **{t['name']}:** {t['detail']}")
    w("")

    # --- Expected-result matrix ---
    w("## Expected-Result Matrix (spec §11)")
    w("")
    w("| Scenario | Condition | F | L | Interpretation |")
    w("|---|---|---|---|---|")
    er_matrix = expected_result_matrix()
    for scenario_id in _SCENARIOS:
        cfg = SCENARIOS[scenario_id]
        f_pos = cfg["f_position"]
        l_pos = cfg["l_position"]
        for cond, vals in er_matrix.items():
            # Compute expected actions for this scenario
            from .oracle import compute_expected_action
            f_exp = compute_expected_action(f_pos, 0)
            l_exp = compute_expected_action(l_pos, 0)
            w(f"| {scenario_id} | {cond} | {f_exp.kind.value}({f_exp.quantity}) | {l_exp.kind.value}({l_exp.quantity}) | {vals['interpretation']} |")
    w("")

    # --- Observed-result matrix per scenario ---
    for scenario_id in _SCENARIOS:
        w(f"## Observed-Result Matrix — {scenario_id}")
        w("")
        w("| Condition | F | L | Paired | Memory Failure | Strategy Failure |")
        w("|---|---|---|---|---|---|")
        for condition in _CONDITIONS:
            key = f"{scenario_id}/{condition}"
            pr = paired.get(key)
            if pr is None:
                w(f"| {condition} | — | — | — | — | — |")
                continue
            f_cls = pr.result_f.classification
            l_cls = pr.result_l.classification
            mem = "YES" if pr.memory_failure else "no"
            strat = "YES" if pr.strategy_failure else "no"
            w(f"| {condition} | {f_cls} | {l_cls} | {pr.paired_classification} | {mem} | {strat} |")
        w("")

    # --- Primary metric ---
    w("## Primary Metric: Paired State-Continuity Success (per scenario)")
    w("")
    for scenario_id in _SCENARIOS:
        w(f"### {scenario_id}")
        w("")
        bf_key = f"{scenario_id}/B-full"
        a_key = f"{scenario_id}/A"
        bf = paired.get(bf_key)
        a_cond = paired.get(a_key)
        if bf and a_cond:
            b_pass = bf.paired_classification == "PASS"
            a_both_pass = a_cond.paired_classification == "PASS"
            paired_gate = b_pass and not a_both_pass
            w(f"- **B-full F:** {bf.result_f.classification}")
            w(f"- **B-full L:** {bf.result_l.classification}")
            w(f"- **B-full paired:** {bf.paired_classification}")
            w(f"- **A F:** {a_cond.result_f.classification}")
            w(f"- **A L:** {a_cond.result_l.classification}")
            w(f"- **A paired:** {a_cond.paired_classification}")
            w(f"- **Paired gate (B-full pass AND A not both-pass):** {'PASS' if paired_gate else 'FAIL'}")
        else:
            w("- **INCOMPLETE:** Missing B-full or A results.")
        w("")

    # --- Secondary metrics ---
    w("## Secondary Metrics (per scenario)")
    w("")
    secondary = [
        ("B-minus", "B-minus fail-closed rate"),
        ("B-minus-explicit", "B-minus-explicit fail-closed rate (explicit instruction)"),
        ("B-corrupt", "B-corrupt rejection rate"),
        ("B-restored", "B-restored recovery to B-full"),
    ]
    for scenario_id in _SCENARIOS:
        w(f"### {scenario_id}")
        w("")
        for cond, desc in secondary:
            key = f"{scenario_id}/{cond}"
            pr = paired.get(key)
            if pr is None:
                w(f"- **{desc}:** — (no result)")
                continue
            w(f"- **{desc}:** {pr.paired_classification}")
        w("")

    # --- Cross-trial consistency ---
    w("## Cross-Trial Consistency (diagnostic)")
    w("")
    inconsistencies = _check_cross_trial_consistency(digests)
    if inconsistencies:
        w(f"**{len(inconsistencies)} condition(s) show cross-trial variation:**")
        w("")
        for inc in inconsistencies:
            w(f"- {inc['scenario_id']}/{inc['condition']}/{inc['episode_id']}: "
              f"{inc['unique_digests']} unique digests across {inc['total_runs']} runs")
            w(f"  - {inc['note']}")
    else:
        w("All trials produced identical digests for each (scenario, condition, episode).")
        w("Note: this may indicate provider-side caching or deterministic model behavior.")
    w("")

    # --- Individual run details ---
    w("## Individual Run Details")
    w("")
    w("| Run ID | Scenario | Trial | Condition | Episode | Action | Qty | Classification | Reasoning |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in all_runs:
        parts = r.run_id.split("-")
        scenario_tag = parts[-1] if parts else "?"
        trial = r.run_id.split("-t")[-1].split("-")[0] if "-t" in r.run_id else "?"
        reasoning = r.worker_output.reasoning[:60] if r.worker_output.reasoning else ""
        reasoning = reasoning.replace("|", "/")  # escape table pipes
        w(f"| {r.run_id} | {scenario_tag} | {trial} | {r.condition} | {r.episode_id}"
          f" | {r.worker_output.action_kind} | {r.worker_output.quantity}"
          f" | {r.classification} | {reasoning} |")
    w("")

    # --- Errors ---
    if errors:
        w("## Errors")
        w("")
        for e in errors:
            w(f"- {e['scenario_id']} trial={e['trial_number']} {e['condition']}/{e['episode_id']}: {e['error']}")
        w("")

    # --- Summary ---
    w("## Summary")
    w("")
    criteria = verify_llm_acceptance_criteria(results)
    passed = sum(1 for _, p, _ in criteria if p)
    total = len(criteria)
    w(f"**{passed}/{total} acceptance criteria passed.**")
    w("")
    for name, ok, detail in criteria:
        mark = "PASS" if ok else "FAIL"
        w(f"- [{mark}] **{name}:** {detail}")
    w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------


def verify_llm_acceptance_criteria(results: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """Check acceptance criteria for V0.2b (all 3 scenarios).

    V0.2b: Each scenario must independently pass the same criteria.
    """
    paired = results["paired_results"]
    criteria: list[tuple[str, bool, str]] = []

    # 1. Isolation audit passed.
    audit = results.get("isolation_audit", {})
    criteria.append((
        "Isolation audit passed",
        audit.get("passed", False),
        "; ".join(f"{t['name']}: {'OK' if t['passed'] else 'FAIL'}"
                  for t in audit.get("tests", [])),
    ))

    # 2. For each scenario: B-full produces correct action for both F and L.
    for scenario_id in _SCENARIOS:
        bf = paired.get(f"{scenario_id}/B-full")
        if bf:
            ok = bf.paired_classification == "PASS"
            criteria.append((f"{scenario_id}: B-full paired pass", ok,
                             f"F={bf.result_f.classification}, L={bf.result_l.classification}"))
        else:
            criteria.append((f"{scenario_id}: B-full paired pass", False, "no result"))

    # 3. For each scenario: A does not pass both episodes.
    for scenario_id in _SCENARIOS:
        a_cond = paired.get(f"{scenario_id}/A")
        if a_cond:
            a_both = a_cond.paired_classification == "PASS"
            ok = not a_both
            detail = "A passes both — LEAKAGE SUSPECTED" if a_both else f"A paired={a_cond.paired_classification}"
            criteria.append((f"{scenario_id}: A must not pass both", ok, detail))
        else:
            criteria.append((f"{scenario_id}: A must not pass both", False, "no result"))

    # 4. For each scenario: B-minus fails closed.
    for scenario_id in _SCENARIOS:
        bm = paired.get(f"{scenario_id}/B-minus")
        if bm:
            f_ok = bm.result_f.classification in {"MISSING_REQUIRED_STATE", "FAIL"}
            l_ok = bm.result_l.classification in {"MISSING_REQUIRED_STATE", "FAIL"}
            ok = f_ok and l_ok
            criteria.append((f"{scenario_id}: B-minus fail-closed", ok,
                             f"F={bm.result_f.classification}, L={bm.result_l.classification}"))
        else:
            criteria.append((f"{scenario_id}: B-minus fail-closed", False, "no result"))

    # 5. For each scenario: B-minus-explicit fails closed with explicit instruction.
    for scenario_id in _SCENARIOS:
        bme = paired.get(f"{scenario_id}/B-minus-explicit")
        if bme:
            f_ok = bme.result_f.classification in {"MISSING_REQUIRED_STATE", "FAIL"}
            l_ok = bme.result_l.classification in {"MISSING_REQUIRED_STATE", "FAIL"}
            ok = f_ok and l_ok
            criteria.append((f"{scenario_id}: B-minus-explicit fail-closed (explicit instruction)", ok,
                             f"F={bme.result_f.classification}, L={bme.result_l.classification}"))
        else:
            criteria.append((f"{scenario_id}: B-minus-explicit fail-closed (explicit instruction)", False, "no result"))

    # 6. For each scenario: B-corrupt is rejected or produces invalid action.
    for scenario_id in _SCENARIOS:
        bc = paired.get(f"{scenario_id}/B-corrupt")
        if bc:
            f_ok = bc.result_f.classification != "PASS"
            l_ok = bc.result_l.classification != "PASS"
            ok = f_ok and l_ok
            criteria.append((f"{scenario_id}: B-corrupt rejection", ok,
                             f"F={bc.result_f.classification}, L={bc.result_l.classification}"))
        else:
            criteria.append((f"{scenario_id}: B-corrupt rejection", False, "no result"))

    # 7. For each scenario: B-restored returns to B-full behavior.
    for scenario_id in _SCENARIOS:
        br = paired.get(f"{scenario_id}/B-restored")
        if br:
            ok = br.paired_classification == "PASS"
            criteria.append((f"{scenario_id}: B-restored recovery", ok,
                             f"F={br.result_f.classification}, L={br.result_l.classification}"))
        else:
            criteria.append((f"{scenario_id}: B-restored recovery", False, "no result"))

    # 8. For each scenario: Condition S produces correct action for both episodes.
    for scenario_id in _SCENARIOS:
        s_cond = paired.get(f"{scenario_id}/S")
        if s_cond:
            ok = s_cond.paired_classification == "PASS"
            criteria.append((f"{scenario_id}: S strategy-control pass", ok,
                             f"F={s_cond.result_f.classification}, L={s_cond.result_l.classification}"))
        else:
            criteria.append((f"{scenario_id}: S strategy-control pass", False, "no result"))

    # 9. No API key leakage.
    model_cfg = results.get("model_config", {})
    has_key = bool(model_cfg.get("api_key"))
    criteria.append((
        "No API key in results",
        not has_key,
        "api_key excluded from model_config" if not has_key else "api_key PRESENT — LEAKAGE",
    ))

    return criteria


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run the full V0.2b experiment and write report + JSON artifacts.

    V0.2b: Outputs to results/v0.2b/ directory to preserve V0.2a and V0.1 artifacts.
    """

    results_dir = Path(_PROJECT_ROOT) / "results" / "v0.2b"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("[llm_runner] Running V0.2b experiment (210 planned LLM calls)...", file=sys.stderr)
    results = run_all_llm_experiments(seed=42)

    if results.get("aborted"):
        print(f"[llm_runner] ABORTED: {results['abort_reason']}", file=sys.stderr)
        return 1

    all_runs = results["all_runs"]
    print(f"[llm_runner] Completed {len(all_runs)} runs.", file=sys.stderr)

    # Write report.
    report = generate_llm_report(results)
    report_path = results_dir / "EXPERIMENT_V0.2b_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"[llm_runner] Report written: {report_path}", file=sys.stderr)

    # Write experiment_v0.2b_results.json.
    run_data = []
    for r in all_runs:
        run_data.append({
            "run_id": r.run_id,
            "condition": r.condition,
            "episode_id": r.episode_id,
            "worker_action": r.worker_output.action_kind,
            "worker_quantity": r.worker_output.quantity,
            "worker_reasoning": r.worker_output.reasoning,
            "worker_raw_text": r.worker_output.raw_text,
            "classification": r.classification,
            "correct_action": r.validation.correct_action,
            "correct_ledger": r.validation.correct_ledger,
            "expected_action": r.validation.expected_action.kind.value,
            "expected_quantity": r.validation.expected_action.quantity,
            "state_fixture_path": r.state_fixture_path,
        })
    json_path = results_dir / "experiment_v0.2b_results.json"
    json_path.write_text(json.dumps(run_data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[llm_runner] Run results written: {json_path}", file=sys.stderr)

    # Write run_digests.json (behavior and response digests).
    digest_path = results_dir / "run_digests.json"
    digest_path.write_text(json.dumps(results["run_digests"], indent=2, sort_keys=True), encoding="utf-8")
    print(f"[llm_runner] Digests written: {digest_path}", file=sys.stderr)

    # Print acceptance criteria.
    criteria = verify_llm_acceptance_criteria(results)
    passed = sum(1 for _, p, _ in criteria if p)
    total = len(criteria)
    print(f"\n[llm_runner] Acceptance criteria: {passed}/{total} passed", file=sys.stderr)
    for name, ok, detail in criteria:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}: {detail}", file=sys.stderr)

    return 0 if passed == total else 1


# ---------------------------------------------------------------------------
# V0.3a report generation
# ---------------------------------------------------------------------------


def generate_v03a_report(results: dict[str, Any]) -> str:
    """Generate the V0.3a experiment report in markdown."""
    paired = results["paired_results"]
    model_cfg = results["model_config"]
    errors = results.get("errors", [])
    split = results.get("split", "dev")
    scenario_specs = results.get("scenario_specs", [])

    lines: list[str] = []
    w = lines.append

    w("# PM1 Trading Benchmark v0.3a — Experiment Report")
    w("")
    w("## Metadata")
    w("")
    w(f"- **Version:** v0.3a")
    w(f"- **Split:** {split}")
    w(f"- **Model:** {model_cfg.get('model', 'unknown')}")
    w(f"- **Provider:** OpenAI-compatible endpoint ({model_cfg.get('base_url', 'unknown')})")
    w(f"- **Temperature:** {model_cfg.get('temperature', 'unknown')}")
    w(f"- **Scenarios:** {len(scenario_specs)}")
    w(f"- **Variants:** {', '.join(TASK_SPEC_VARIANTS)}")
    w(f"- **Conditions:** {', '.join(_CONDITIONS_V03A)}")
    w(f"- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    w(f"- **Total planned calls:** {len(scenario_specs) * len(_EPISODES) * len(_CONDITIONS_V03A) * len(TASK_SPEC_VARIANTS)}")
    w(f"- **Total successful runs:** {len(results['all_runs'])}")
    w(f"- **Total errors:** {len(errors)}")
    w("")

    # --- Scenario matrix ---
    w("## Scenario Matrix")
    w("")
    w(scenario_matrix_table())
    w("")

    # --- Variant descriptions ---
    w("## Task-Spec Variants")
    w("")
    for i, variant in enumerate(TASK_SPEC_VARIANTS):
        w(f"### Variant {i+1}: {variant['name']}")
        w("")
        w(f"- **Goal:** {variant['goal']}")
        w(f"- **Rules:** {variant['rules']}")
        w(f"- **Output format:** {variant['output_format']}")
        w("")

    # --- Results per scenario ---
    w("## Results by Scenario")
    w("")
    w("| Scenario | Variant | Condition | F | L | Paired |")
    w("|---|---|---|---|---|---|")
    for spec_dict in scenario_specs:
        sid = spec_dict["scenario_id"]
        for variant in TASK_SPEC_VARIANTS:
            for condition in _CONDITIONS_V03A:
                key = f"{sid}/{variant['name']}/{condition}"
                pr = paired.get(key)
                if pr:
                    f_cls = pr.result_f.classification
                    l_cls = pr.result_l.classification
                    paired_cls = pr.paired_classification
                else:
                    f_cls = l_cls = paired_cls = "—"
                w(f"| {sid} | {variant['name']} | {condition} | {f_cls} | {l_cls} | {paired_cls} |")
    w("")

    # --- Coverage analysis ---
    w("## Coverage Analysis")
    w("")

    # Compute action coverage
    action_coverage = {"BUY": False, "SELL": False, "HOLD": False}
    for spec_dict in scenario_specs:
        for ep_key in ("F", "L"):
            ep_data = spec_dict["episodes"][ep_key]
            # Determine expected action
            from lib.oracle import compute_expected_action
            f_pos = spec_dict["episodes"]["F"]["position_qty"]
            target = spec_dict["observation"]["target_signal"]
            expected = compute_expected_action(f_pos, target)
            action_coverage[expected.kind.value] = True

    w("### Action Coverage")
    w("")
    for action, covered in action_coverage.items():
        mark = "✓" if covered else "✗"
        w(f"- {mark} {action}")
    w("")

    # --- Errors ---
    if errors:
        w("## Errors")
        w("")
        for e in errors:
            w(f"- {e['scenario_id']} {e['variant']} {e['condition']}/{e['episode_id']}: {e['error']}")
        w("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# V0.3a main
# ---------------------------------------------------------------------------


def main_v03a() -> int:
    """Run V0.3a experiments and write report + JSON artifacts.

    V0.3a: Runs dev set (18 scenarios) and held-out set (6 scenarios) separately.
    Outputs to results/v0.3a/ directory.
    """
    results_dir = Path(_PROJECT_ROOT) / "results" / "v0.3a"
    results_dir.mkdir(parents=True, exist_ok=True)

    model_config = get_model_config()

    # Run dev set
    print("[llm_runner] Running V0.3a dev set (648 planned LLM calls)...", file=sys.stderr)
    dev_results = run_v03a_experiments(split="dev", model_config=model_config)
    print(f"[llm_runner] Dev set completed: {len(dev_results['all_runs'])} runs.", file=sys.stderr)

    # Write dev results
    dev_report = generate_v03a_report(dev_results)
    (results_dir / "EXPERIMENT_V0.3a_DEV_REPORT.md").write_text(dev_report, encoding="utf-8")

    dev_run_data = []
    for r in dev_results["all_runs"]:
        dev_run_data.append({
            "run_id": r.run_id,
            "condition": r.condition,
            "episode_id": r.episode_id,
            "worker_action": r.worker_output.action_kind,
            "worker_quantity": r.worker_output.quantity,
            "worker_reasoning": r.worker_output.reasoning,
            "classification": r.classification,
            "correct_action": r.validation.correct_action,
            "correct_ledger": r.validation.correct_ledger,
            "expected_action": r.validation.expected_action.kind.value,
            "expected_quantity": r.validation.expected_action.quantity,
        })
    (results_dir / "experiment_v0.3a_dev_results.json").write_text(
        json.dumps(dev_run_data, indent=2, sort_keys=True), encoding="utf-8"
    )
    (results_dir / "dev_run_digests.json").write_text(
        json.dumps(dev_results["run_digests"], indent=2, sort_keys=True), encoding="utf-8"
    )

    # Run held-out set
    print("[llm_runner] Running V0.3a held-out set (216 planned LLM calls)...", file=sys.stderr)
    heldout_results = run_v03a_experiments(split="held-out", model_config=model_config)
    print(f"[llm_runner] Held-out set completed: {len(heldout_results['all_runs'])} runs.", file=sys.stderr)

    # Write held-out results
    heldout_report = generate_v03a_report(heldout_results)
    (results_dir / "EXPERIMENT_V0.3a_HELDOUT_REPORT.md").write_text(heldout_report, encoding="utf-8")

    heldout_run_data = []
    for r in heldout_results["all_runs"]:
        heldout_run_data.append({
            "run_id": r.run_id,
            "condition": r.condition,
            "episode_id": r.episode_id,
            "worker_action": r.worker_output.action_kind,
            "worker_quantity": r.worker_output.quantity,
            "worker_reasoning": r.worker_output.reasoning,
            "classification": r.classification,
            "correct_action": r.validation.correct_action,
            "correct_ledger": r.validation.correct_ledger,
            "expected_action": r.validation.expected_action.kind.value,
            "expected_quantity": r.validation.expected_action.quantity,
        })
    (results_dir / "experiment_v0.3a_heldout_results.json").write_text(
        json.dumps(heldout_run_data, indent=2, sort_keys=True), encoding="utf-8"
    )
    (results_dir / "heldout_run_digests.json").write_text(
        json.dumps(heldout_results["run_digests"], indent=2, sort_keys=True), encoding="utf-8"
    )

    print(f"[llm_runner] All V0.3a results written to {results_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
