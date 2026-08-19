"""
Scenario manifest for PM1 Trading Benchmark v0.1 / v0.2a / v0.2b / v0.3a.

Two matched episodes (F and L) share identical worker-visible observations
but differ in hidden prior state. The seed determines episode fixtures and
deterministic identifiers only — no external market data.

V0.2a adds scenario_id to distinguish scenarios without leaking identity
into worker prompts.

V0.2b adds multi-scenario support: S1, S2, S3 with different position/target
configurations to test generalization.

V0.3a adds policy_variant field for task-spec variant tracking. Generated
scenarios (24 total) are produced by lib/scenario_generator.py, not by
make_scenario(). The make_scenario() function remains for V0.2b backward
compatibility.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "ActionKind",
    "Action",
    "Episode",
    "Observation",
    "Scenario",
    "SCENARIOS",
    "make_scenario",
    "expected_result_matrix",
]


class ActionKind(Enum):
    """Permitted actions in the benchmark action contract."""

    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Action:
    """A structured worker action."""

    kind: ActionKind
    quantity: int = 0


@dataclass(frozen=True)
class Episode:
    """Hidden fixture and expected result for one matched episode."""

    id: str
    hidden_position_qty: int
    hidden_cash_cents: int
    expected_action: Action
    expected_ledger: dict[str, int]


@dataclass(frozen=True)
class Observation:
    """The observation shared byte-for-byte by both episodes."""

    instrument: str = "XYZ"
    price_cents: int = 10000
    target_signal: int = 0
    logical_tick: int = 1


@dataclass(frozen=True)
class Scenario:
    """Complete deterministic benchmark manifest.

    V0.2a adds scenario_id for experiment-level identification. The
    scenario_id must NOT appear in any worker-facing prompt — it is
    an experiment-traceability field only.

    V0.3a adds policy_variant to track which task-spec variant is used.
    """

    version: str
    seed: int
    episodes: dict[str, Episode]
    observation: Observation
    task_spec: str
    scenario_id: str = "S1"
    policy_variant: str = "canonical"


TASK_SPEC = (
    "Policy: set position_qty equal to target_signal. Use BUY 1 when "
    "position_qty is below target_signal, SELL 1 when position_qty is "
    "above target_signal, and HOLD when they are equal. Return exactly one "
    "action: BUY 1, SELL 1, or HOLD."
)

# V0.2b: Scenario configurations.
# Each scenario defines position_qty for F and L episodes, the target_signal,
# expected actions, and the B-corrupt position (always wrong for that episode).
# Cash is derived: cash_cents = 10000 - position_qty * price_cents.
SCENARIOS: dict[str, dict[str, Any]] = {
    "S1": {
        "f_position": 0,
        "l_position": 1,
        "target_signal": 0,
        "f_expected_action": "HOLD",
        "f_expected_qty": 0,
        "l_expected_action": "SELL",
        "l_expected_qty": 1,
        "corrupt_f": 1,   # 1 - 0 = 1 (flip from true 0)
        "corrupt_l": 0,   # 1 - 1 = 0 (flip from true 1)
    },
    "S2": {
        "f_position": 0,
        "l_position": 2,
        "target_signal": 1,
        "f_expected_action": "BUY",
        "f_expected_qty": 1,
        "l_expected_action": "SELL",
        "l_expected_qty": 1,
        "corrupt_f": 1,   # wrong: true is 0, target is 1, corrupt=1 makes position==target → HOLD
        "corrupt_l": 1,   # wrong: true is 2, target is 1, corrupt=1 makes BUY instead of SELL
    },
    "S3": {
        "f_position": 2,
        "l_position": 0,
        "target_signal": 1,
        "f_expected_action": "SELL",
        "f_expected_qty": 1,
        "l_expected_action": "BUY",
        "l_expected_qty": 1,
        "corrupt_f": 1,   # wrong: true is 2, target is 1, corrupt=1 makes HOLD instead of SELL
        "corrupt_l": 1,   # wrong: true is 0, target is 1, corrupt=1 makes HOLD instead of BUY
    },
}


def make_scenario(seed: int = 42, scenario_id: str = "S1") -> Scenario:
    """Create the versioned, deterministic two-episode scenario.

    V0.2a: scenario_id identifies the scenario in experiment traces.
    It must NOT be included in worker-facing prompts.

    V0.2b: Supports S1, S2, S3 with different position/target configurations.
    """
    if scenario_id not in SCENARIOS:
        raise ValueError(f"unknown scenario_id: {scenario_id!r}; expected one of {list(SCENARIOS)}")

    cfg = SCENARIOS[scenario_id]
    f_pos = cfg["f_position"]
    l_pos = cfg["l_position"]
    target = cfg["target_signal"]
    price = 10000

    observation = Observation(target_signal=target)
    f_cash = 10000 - f_pos * price
    l_cash = 10000 - l_pos * price

    f_action_kind = ActionKind[cfg["f_expected_action"]]
    l_action_kind = ActionKind[cfg["l_expected_action"]]
    f_qty = cfg["f_expected_qty"]
    l_qty = cfg["l_expected_qty"]

    initial_ledger = {"cash_cents": 10000, "position_qty": 0}

    episodes = {
        "F": Episode(
            id="F",
            hidden_position_qty=f_pos,
            hidden_cash_cents=f_cash,
            expected_action=Action(f_action_kind, f_qty),
            expected_ledger=initial_ledger.copy(),
        ),
        "L": Episode(
            id="L",
            hidden_position_qty=l_pos,
            hidden_cash_cents=l_cash,
            expected_action=Action(l_action_kind, l_qty),
            expected_ledger=initial_ledger.copy(),
        ),
    }
    return Scenario(
        version="0.2b",
        seed=seed,
        episodes=episodes,
        observation=observation,
        task_spec=TASK_SPEC,
        scenario_id=scenario_id,
    )


def expected_result_matrix() -> dict[str, dict[str, str]]:
    """Return the expected-result matrix from experiment specification.

    V0.2b: Returns S1-specific matrix (target=0). S2/S3 have different expected actions.
    """
    return {
        "A, no state": {
            "F": "guess/fail",
            "L": "guess/fail",
            "interpretation": "must not pass both; if it does, investigate leakage",
        },
        "B-full": {"F": "HOLD", "L": "SELL 1", "interpretation": "required continuation pass"},
        "B-minus": {"F": "fail closed", "L": "fail closed", "interpretation": "required missing-state detection"},
        "B-corrupt": {"F": "reject/invalid", "L": "reject/invalid", "interpretation": "must not count as normal pass"},
        "B-restored": {"F": "HOLD", "L": "SELL 1", "interpretation": "required restoration pass"},
        "S, complete state": {"F": "HOLD", "L": "SELL 1", "interpretation": "required strategy-control pass"},
    }


if __name__ == "__main__":
    # V0.2a: S1 checks
    scenario = make_scenario()
    assert scenario.episodes["F"].expected_action == Action(ActionKind.HOLD)
    assert scenario.episodes["L"].expected_action == Action(ActionKind.SELL, 1)
    assert scenario.episodes["F"].expected_ledger == scenario.episodes["L"].expected_ledger
    assert scenario.observation.target_signal == 0
    assert scenario.task_spec == TASK_SPEC
    assert scenario.scenario_id == "S1"
    # V0.2a: test custom scenario_id
    scenario_custom = make_scenario(scenario_id="S2")
    assert scenario_custom.scenario_id == "S2"
    # V0.2b: S2 checks
    s2 = make_scenario(scenario_id="S2")
    assert s2.observation.target_signal == 1
    assert s2.episodes["F"].hidden_position_qty == 0
    assert s2.episodes["L"].hidden_position_qty == 2
    assert s2.episodes["F"].expected_action == Action(ActionKind.BUY, 1)
    assert s2.episodes["L"].expected_action == Action(ActionKind.SELL, 1)
    # V0.2b: S3 checks
    s3 = make_scenario(scenario_id="S3")
    assert s3.observation.target_signal == 1
    assert s3.episodes["F"].hidden_position_qty == 2
    assert s3.episodes["L"].hidden_position_qty == 0
    assert s3.episodes["F"].expected_action == Action(ActionKind.SELL, 1)
    assert s3.episodes["L"].expected_action == Action(ActionKind.BUY, 1)
    print("scenario checks passed")
