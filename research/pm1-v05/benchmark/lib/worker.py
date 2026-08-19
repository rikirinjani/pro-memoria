"""
Worker harness for PM1 Trading Benchmark v0.1 / v0.2a / v0.2b / v0.3a.

Spawns fresh worker processes for each condition. Invokes the context
assembler for condition B. Handles conditions A, B, and S.

V0.2b: Scenario-aware fixture creation and worker execution.
V0.3a: Accepts Scenario objects directly for generated scenarios.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from .scenario import ActionKind, Observation, Scenario, make_scenario, SCENARIOS
    from .fixtures import create_state_dir
    from .oracle import compute_expected_action
    from .validator import WorkerOutput
except ImportError:  # Allow running this file directly from the lib directory.
    from scenario import ActionKind, Observation, Scenario, make_scenario, SCENARIOS
    from fixtures import create_state_dir
    from oracle import compute_expected_action
    from validator import WorkerOutput

__all__ = [
    "build_worker_inputs",
    "invoke_context_assembler",
    "execute_worker",
    "format_observation",
]


def format_observation(observation: Observation) -> str:
    """Format observation as the worker-visible text block."""
    return (
        f"instrument = {observation.instrument}\n"
        f"price_cents = {observation.price_cents}\n"
        f"target_signal = {observation.target_signal}\n"
        f"logical_tick = {observation.logical_tick}"
    )


def _condition_key(condition: str) -> str:
    """Normalize condition labels while preserving the B variant."""
    return condition.strip().upper().replace("_", "-").split(",", 1)[0]


def invoke_context_assembler(state_dir: str, scenario: Scenario) -> dict[str, Any]:
    """Invoke the existing context assembler and return its packet mapping."""
    # This also makes the harness runnable from a checkout without installation.
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from morse.context_assembly import assembler

    task_spec_dict = {
        "task_id": "pm1-trading-benchmark-v0.1",
        "relevant_tags": ["relevant", "trading"],
        "spec_ref": "pm1-trading-benchmark/EXPERIMENT_V0.1.md",
        "brief": scenario.task_spec,
        "required_outputs": ["action"],
    }
    packet = assembler.assemble(
        task_spec_dict,
        "opencode/gpt-5.6-luna",
        state_dir,
    )
    return packet.to_dict()


def build_worker_inputs(
    condition: str,
    episode_id: str,
    scenario: Scenario,
    state_dir: str | None = None,
    scenario_id: str = "S1",
) -> dict[str, Any]:
    """Build the complete worker-visible input set for one condition.

    V0.2a: B-minus-explicit creates the same fixture as B-minus but
    the system prompt will include an explicit fail-closed instruction.

    V0.2b: Scenario-aware fixture creation.

    V0.3a: Uses Scenario object for fixture creation when available.
    """
    key = _condition_key(condition)
    if episode_id not in scenario.episodes:
        raise ValueError(f"unknown episode_id: {episode_id!r}")

    packet: dict[str, Any] | None = None
    prior_context: str | None = None
    direct_state: str | None = None
    fixture_path: str | None = None

    if key in {"B", "B-FULL", "B-MINUS", "B-MINUS-EXPLICIT", "B-CORRUPT", "B-RESTORED"}:
        # B-minus-explicit uses the same fixture as B-minus (position_qty absent)
        variant = "B-full" if key == "B" else key
        if variant == "B-MINUS-EXPLICIT":
            variant = "B-minus"
        fixture_path = state_dir
        if fixture_path is None:
            base_dir = tempfile.mkdtemp(prefix="pm1-worker-")
            # V0.2b: Use scenario object for fixture creation (already has correct positions
            # for V0.3a generated scenarios; for V0.2b S1/S2/S3, positions come from SCENARIOS
            # dict via the scenario object passed by llm_runner).
            fixture_path = create_state_dir(base_dir, variant, episode_id, scenario_id, scenario=scenario)
        packet = invoke_context_assembler(fixture_path, scenario)
    elif key == "S":
        # V0.2b/V0.3a: Use scenario_id to get the correct position for S condition.
        # For V0.2b (S1/S2/S3), look up from SCENARIOS dict.
        # For V0.3a (GS001+), use Scenario object.
        ep_key = episode_id.upper()
        if scenario_id in SCENARIOS:
            # V0.2b: Look up from SCENARIOS dict
            cfg = SCENARIOS[scenario_id]
            position = cfg["f_position"] if ep_key == "F" else cfg["l_position"]
        else:
            # V0.3a: Use Scenario object directly
            position = scenario.episodes[ep_key].hidden_position_qty
        direct_state = f"position_qty = {position}"
    elif key != "A":
        raise ValueError(f"unknown worker condition: {condition!r}")

    return {
        "task_spec": scenario.task_spec,
        "observation": format_observation(scenario.observation),
        "packet": packet,
        "prior_context": prior_context,
        "direct_state": direct_state,
        "state_dir": fixture_path,
    }


def _packet_position(packet: dict[str, Any]) -> int | None:
    """Find position_qty in assembled project-state records."""
    for section in packet.get("sections", []):
        for record in section.get("records", []):
            payload = record.get("payload", {})
            if "position_qty" in payload:
                value = payload["position_qty"]
                return value if isinstance(value, int) and not isinstance(value, bool) else None
    return None


def _position_from_text(text: str | None) -> int | None:
    if not text:
        return None
    marker = "position_qty ="
    if marker not in text:
        return None
    value = text.split(marker, 1)[1].strip().split()[0]
    try:
        return int(value)
    except (ValueError, IndexError):
        return None


def execute_worker(
    inputs: dict[str, Any],
    condition: str,
    episode_id: str,
    scenario_id: str = "S1",
    scenario: Scenario | None = None,
) -> WorkerOutput:
    """Execute the deterministic worker policy for the supplied inputs.

    V0.2a: B-minus-explicit behaves the same as B-minus at the worker
    level (position is None → MISSING_REQUIRED_STATE). The explicit
    fail-closed instruction is in the system prompt.

    V0.2b: Uses scenario_id to look up the correct target_signal.

    V0.3a: Accepts optional Scenario object directly (takes precedence
    over scenario_id lookup). This allows generated scenarios from
    scenario_generator to be used without going through SCENARIOS dict.
    """
    key = _condition_key(condition)
    position: int | None
    if key in {"B", "B-FULL", "B-CORRUPT", "B-RESTORED"}:
        position = _packet_position(inputs.get("packet") or {})
    elif key == "C":
        position = _position_from_text(inputs.get("prior_context"))
    elif key == "S":
        position = _position_from_text(inputs.get("direct_state"))
    elif key == "A":
        position = None
    elif key in {"B-MINUS", "B-MINUS-EXPLICIT"}:
        position = None
    else:
        raise ValueError(f"unknown worker condition: {condition!r}")

    if position is None:
        if key in {"B-MINUS", "B-MINUS-EXPLICIT"}:
            return WorkerOutput("MISSING_REQUIRED_STATE", 0, "position_qty is missing")
        return WorkerOutput(ActionKind.HOLD.value, 0, "position_qty unavailable; default HOLD")

    # V0.2b/V0.3a: Use scenario_id for V0.2b (S1/S2/S3), scenario object for V0.3a (GS001+).
    if scenario_id in SCENARIOS:
        # V0.2b: Look up from SCENARIOS dict
        target_signal = SCENARIOS[scenario_id]["target_signal"]
    elif scenario is not None:
        # V0.3a: Use Scenario object directly
        target_signal = scenario.observation.target_signal
    else:
        raise ValueError(f"unknown scenario_id: {scenario_id!r}")
    action = compute_expected_action(position, target_signal)
    return WorkerOutput(action.kind.value, action.quantity, f"position_qty={position}")


if __name__ == "__main__":
    scenario = make_scenario()
    conditions = ("A", "B-full", "B-minus", "B-minus-explicit", "B-corrupt", "B-restored", "S")
    for scenario_id in ("S1", "S2", "S3"):
        for condition in conditions:
            for episode_id in ("F", "L"):
                worker_inputs = build_worker_inputs(condition, episode_id, scenario, scenario_id=scenario_id)
                output = execute_worker(worker_inputs, condition, episode_id, scenario_id=scenario_id)
                print(scenario_id, condition, episode_id, output.action_kind, output.quantity)
