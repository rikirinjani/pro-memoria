"""
Independent oracle for PM1 Trading Benchmark v0.1.

Owns the truth manifest. Validates worker actions against hidden state.
Must not import worker policy, consume PM-Adapter output as truth, or
derive expected actions from worker reasoning.
"""

from dataclasses import dataclass

try:
    from .scenario import Action, ActionKind, Episode, Observation, make_scenario
except ImportError:  # Allow running this file directly from the lib directory.
    from scenario import Action, ActionKind, Episode, Observation, make_scenario

__all__ = [
    "ValidationResult",
    "compute_expected_action",
    "apply_ledger",
    "validate_action",
    "classify_outcome",
]


@dataclass(frozen=True)
class ValidationResult:
    """Episode-level independent validation result."""

    correct_action: bool
    correct_ledger: bool
    classification: str
    expected_action: Action
    expected_ledger: dict[str, int]
    worker_action: Action
    detail: str


def compute_expected_action(position_qty: int, target_signal: int) -> Action:
    """Oracle computes correct action from hidden state. No worker input."""

    if position_qty < target_signal:
        return Action(ActionKind.BUY, 1)
    if position_qty > target_signal:
        return Action(ActionKind.SELL, 1)
    return Action(ActionKind.HOLD)


def apply_ledger(ledger: dict[str, int], action: Action, price_cents: int) -> dict[str, int]:
    """Apply one deterministic action and return a new ledger state."""

    result = dict(ledger)
    if action.kind is ActionKind.BUY:
        result["cash_cents"] -= price_cents * action.quantity
        result["position_qty"] += action.quantity
    elif action.kind is ActionKind.SELL:
        result["cash_cents"] += price_cents * action.quantity
        result["position_qty"] -= action.quantity
    elif action.kind is not ActionKind.HOLD:
        raise ValueError(f"unsupported action kind: {action.kind!r}")
    return result


def validate_action(
    action: Action,
    episode: Episode,
    observation: Observation,
) -> ValidationResult:
    """Validate a worker action against independently computed hidden truth."""

    expected_action = compute_expected_action(
        episode.hidden_position_qty, observation.target_signal
    )
    initial_ledger = {
        "cash_cents": episode.hidden_cash_cents,
        "position_qty": episode.hidden_position_qty,
    }
    expected_ledger = apply_ledger(initial_ledger, expected_action, observation.price_cents)

    valid_shape = (
        isinstance(action, Action)
        and isinstance(action.kind, ActionKind)
        and isinstance(action.quantity, int)
        and ((action.kind is ActionKind.HOLD and action.quantity == 0)
             or (action.kind in (ActionKind.BUY, ActionKind.SELL) and action.quantity == 1))
    )
    if not valid_shape:
        return ValidationResult(
            False, False, "INVALID_ACTION", expected_action, expected_ledger,
            action, "Worker action has an invalid kind or quantity.",
        )

    correct_action = action == expected_action
    worker_ledger = apply_ledger(initial_ledger, action, observation.price_cents)
    correct_ledger = worker_ledger == expected_ledger
    classification = "PASS" if correct_action and correct_ledger else "FAIL"
    detail = (
        "Worker action and resulting ledger match oracle truth."
        if classification == "PASS"
        else "Worker action or resulting ledger does not match oracle truth."
    )
    return ValidationResult(
        correct_action, correct_ledger, classification, expected_action,
        expected_ledger, action, detail,
    )


def classify_outcome(
    validation_f: ValidationResult,
    validation_l: ValidationResult,
    condition: str,
) -> str:
    """Classify the paired episode outcome."""

    del condition  # Reserved for condition-specific reporting by callers.
    if validation_f.classification in {"INVALID_ACTION", "INCONCLUSIVE"} or validation_l.classification in {"INVALID_ACTION", "INCONCLUSIVE"}:
        return "INCONCLUSIVE"
    f_pass = validation_f.classification == "PASS"
    l_pass = validation_l.classification == "PASS"
    if f_pass and l_pass:
        return "PASS"
    if f_pass != l_pass:
        return "PARTIAL"
    return "FAIL"


if __name__ == "__main__":
    scenario = make_scenario()
    result_f = validate_action(Action(ActionKind.HOLD), scenario.episodes["F"], scenario.observation)
    result_l = validate_action(Action(ActionKind.SELL, 1), scenario.episodes["L"], scenario.observation)
    assert result_f.classification == "PASS"
    assert result_l.classification == "PASS"
    assert classify_outcome(result_f, result_l, "B-full") == "PASS"
    assert result_f.expected_ledger == {"cash_cents": 10000, "position_qty": 0}
    assert result_l.expected_ledger == {"cash_cents": 10000, "position_qty": 0}
    print("oracle checks passed")
