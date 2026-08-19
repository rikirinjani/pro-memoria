"""
Validation framework for PM1 Trading Benchmark v0.1 / v0.2a.

Classifies worker output against independent oracle truth.
Produces structured run results and paired outcome assessments.

V0.2a adds:
- MISSING_REQUIRED_STATE as a valid classification for B-minus conditions
- trial_number in run_id generation
- B-minus-explicit support
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

try:
    from .scenario import Action, ActionKind, Scenario
    from .oracle import (
        ValidationResult,
        classify_outcome,
        compute_expected_action,
        apply_ledger,
        validate_action,
    )
except ImportError:  # Allow running this file directly from the lib directory.
    from scenario import Action, ActionKind, Scenario
    from oracle import (
        ValidationResult,
        classify_outcome,
        compute_expected_action,
        apply_ledger,
        validate_action,
    )

__all__ = [
    "WorkerOutput",
    "RunResult",
    "PairedResult",
    "parse_worker_output",
    "validate_run",
    "validate_paired",
    "should_count_as_pass",
    "generate_run_id",
]


@dataclass(frozen=True)
class WorkerOutput:
    """Structured action output from a worker."""

    action_kind: str
    quantity: int
    reasoning: str = ""
    raw_text: str = ""


@dataclass(frozen=True)
class RunResult:
    """Result of a single experiment run."""

    run_id: str
    condition: str
    episode_id: str
    worker_output: WorkerOutput
    validation: ValidationResult
    state_fixture_path: str
    assembled_packet_path: str | None
    classification: str
    is_replay: bool


@dataclass(frozen=True)
class PairedResult:
    """Result of paired F+L episodes for one condition."""

    condition: str
    result_f: RunResult
    result_l: RunResult
    paired_classification: str
    memory_failure: bool
    strategy_failure: bool
    mixed_failure: bool


def _json_object(raw_text: str) -> dict[str, Any] | None:
    """Return the first JSON object in worker output, if one exists."""

    candidates = [raw_text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            try:
                value, _ = decoder.raw_decode(candidate[candidate.find("{"):])
            except (ValueError, json.JSONDecodeError):
                continue
        if isinstance(value, dict):
            return value
    return None


def parse_worker_output(raw_text: str) -> WorkerOutput:
    """Parse a worker response into the benchmark's strict action contract."""

    raw = raw_text if isinstance(raw_text, str) else str(raw_text)
    parsed = _json_object(raw)
    if parsed is not None:
        value = parsed.get("action", parsed.get("action_kind"))
        quantity = parsed.get("quantity", 0)
        if isinstance(value, str):
            kind = value.strip().upper()
            if kind in {"HOLD", "BUY", "SELL"}:
                expected_quantity = 0 if kind == "HOLD" else 1
                if quantity == expected_quantity:
                    return WorkerOutput(kind, expected_quantity, raw_text=raw)
        return WorkerOutput("INVALID", 0, raw_text=raw)

    first_line = raw.splitlines()[0] if raw.splitlines() else raw
    match = re.search(r"\b(BUY|SELL)(?:\s+([+-]?\d+))?\b|\b(HOLD)\b", first_line, re.IGNORECASE)
    if match:
        kind = (match.group(1) or match.group(3)).upper()
        number = match.group(2)
        quantity = int(number) if number is not None else (0 if kind == "HOLD" else 1)
        if quantity == (0 if kind == "HOLD" else 1):
            return WorkerOutput(kind, quantity, raw_text=raw)
    return WorkerOutput("INVALID", 0, raw_text=raw)


def validate_run(
    run_id: str,
    condition: str,
    episode_id: str,
    worker_output: WorkerOutput,
    scenario: Scenario,
    state_fixture_path: str,
    assembled_packet_path: str | None = None,
    is_replay: bool = False,
) -> RunResult:
    """Validate one worker run against the independent oracle.

    V0.2a: Handles MISSING_REQUIRED_STATE as a valid classification.
    For B-minus and B-minus-explicit conditions, MISSING_REQUIRED_STATE
    is the expected correct response when position_qty is absent.
    """

    # V0.2a: Handle MISSING_REQUIRED_STATE as a special case
    if worker_output.action_kind == "MISSING_REQUIRED_STATE":
        key = condition.strip().upper().replace("_", "-").split(",", 1)[0]
        if key in {"B-MINUS", "B-MINUS-EXPLICIT"}:
            # MISSING_REQUIRED_STATE is the correct response for B-minus conditions
            episode = scenario.episodes[episode_id]
            expected_action = compute_expected_action(
                episode.hidden_position_qty, scenario.observation.target_signal
            )
            initial_ledger = {
                "cash_cents": episode.hidden_cash_cents,
                "position_qty": episode.hidden_position_qty,
            }
            expected_ledger = apply_ledger(initial_ledger, expected_action, scenario.observation.price_cents)
            action = Action(ActionKind.HOLD, 0)  # placeholder for expected
            validation = ValidationResult(
                correct_action=False,  # Not a normal action match
                correct_ledger=False,  # No ledger transition
                classification="MISSING_REQUIRED_STATE",
                expected_action=expected_action,
                expected_ledger=expected_ledger,
                worker_action=action,
                detail="Worker correctly detected missing required state field.",
            )
            return RunResult(
                run_id=run_id,
                condition=condition,
                episode_id=episode_id,
                worker_output=worker_output,
                validation=validation,
                state_fixture_path=state_fixture_path,
                assembled_packet_path=assembled_packet_path,
                classification="MISSING_REQUIRED_STATE",
                is_replay=is_replay,
            )

    kind_map = {member.value: member for member in ActionKind}
    kind = kind_map.get(worker_output.action_kind.upper())
    action = Action(kind, worker_output.quantity) if kind is not None else Action(ActionKind.HOLD, -1)
    try:
        episode = scenario.episodes[episode_id]
    except KeyError as error:
        raise ValueError(f"unknown episode_id: {episode_id!r}") from error
    validation = validate_action(action, episode, scenario.observation)
    return RunResult(
        run_id=run_id,
        condition=condition,
        episode_id=episode_id,
        worker_output=worker_output,
        validation=validation,
        state_fixture_path=state_fixture_path,
        assembled_packet_path=assembled_packet_path,
        classification=validation.classification,
        is_replay=is_replay,
    )


def _condition_key(condition: str) -> str:
    return condition.strip().upper().split(",", 1)[0]


def validate_paired(condition: str, result_f: RunResult, result_l: RunResult) -> PairedResult:
    """Classify a pair and identify state, strategy, or ambiguous failures.

    V0.2a: Handles MISSING_REQUIRED_STATE classification for B-minus conditions.
    """

    paired = classify_outcome(result_f.validation, result_l.validation, condition)
    key = _condition_key(condition)

    # V0.2a: Handle MISSING_REQUIRED_STATE for B-minus conditions
    if key in {"B-MINUS", "B-MINUS-EXPLICIT"}:
        f_ok = result_f.classification == "MISSING_REQUIRED_STATE"
        l_ok = result_l.classification == "MISSING_REQUIRED_STATE"
        if f_ok and l_ok:
            paired = "PASS"  # Both correctly detected missing state
        elif f_ok or l_ok:
            paired = "PARTIAL"  # Only one detected missing state
        else:
            paired = "FAIL"  # Neither detected missing state

    state_ablation = key in {"B-MINUS", "B-MINUS-EXPLICIT", "B-CORRUPT"}
    memory_failure = (key == "B-FULL" and paired != "PASS") or (state_ablation and paired == "PASS")
    strategy_failure = key == "S" and paired != "PASS"
    mixed_failure = paired == "INCONCLUSIVE" or key not in {
        "A", "B-FULL", "B-MINUS", "B-MINUS-EXPLICIT", "B-CORRUPT", "B-RESTORED", "C", "S"
    }
    return PairedResult(condition, result_f, result_l, paired, memory_failure, strategy_failure, mixed_failure)


def should_count_as_pass(paired: PairedResult) -> bool:
    """Return whether a paired outcome is a counted continuation success.

    V0.2a: Includes B-minus-explicit as a valid condition for pass counting.
    """

    return paired.paired_classification == "PASS" and _condition_key(paired.condition) in {
        "B-FULL", "B-RESTORED", "C", "S"
    } and not paired.memory_failure and not paired.strategy_failure


def generate_run_id(condition: str, episode_id: str, trial_number: int, scenario_id: str = "S1", variant: str = "") -> str:
    """Generate a deterministic run identifier.

    V0.2a: Uses trial_number instead of seed for experiment-level identification.
    V0.3a: Adds optional variant suffix for task-spec variant tracking.
    run_id is purely a traceability identifier — it must NOT appear in worker prompts.
    """
    base = f"run-{scenario_id}-{condition}-{episode_id}-t{trial_number:02d}"
    if variant:
        return f"{base}-{variant}"
    return base


if __name__ == "__main__":
    try:
        from .scenario import make_scenario
    except ImportError:
        from scenario import make_scenario

    scenario = make_scenario()
    assert parse_worker_output('{"action": "BUY", "quantity": 1}').action_kind == "BUY"
    assert parse_worker_output("SELL 1\nextra reasoning").quantity == 1
    assert parse_worker_output("nonsense").action_kind == "INVALID"
    f = validate_run("f", "S", "F", parse_worker_output("HOLD"), scenario, "")
    l = validate_run("l", "S", "L", parse_worker_output("SELL 1"), scenario, "")
    assert should_count_as_pass(validate_paired("S", f, l))
    # V0.2a: Test MISSING_REQUIRED_STATE validation
    from .worker import WorkerOutput as WO
    mr = validate_run("mr", "B-minus", "F", WO("MISSING_REQUIRED_STATE", 0, "position_qty is missing"), scenario, "")
    assert mr.classification == "MISSING_REQUIRED_STATE"
    mr2 = validate_run("mr2", "B-minus", "L", WO("MISSING_REQUIRED_STATE", 0, "position_qty is missing"), scenario, "")
    assert mr2.classification == "MISSING_REQUIRED_STATE"
    paired = validate_paired("B-minus", mr, mr2)
    assert paired.paired_classification == "PASS"
    # V0.2a: Test generate_run_id with trial_number
    rid = generate_run_id("B-full", "F", 3, "S1")
    assert rid == "run-S1-B-full-F-t03"
    print("validator checks passed")
