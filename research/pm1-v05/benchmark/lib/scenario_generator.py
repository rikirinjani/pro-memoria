"""
Deterministic scenario generator for PM1 Trading Benchmark v0.3a.

Produces 24 curated scenarios from a generator seed, covering:
- HOLD, BUY, SELL actions across episodes
- Negative positions (short selling), zero, positive positions
- Multi-unit position differences (|pos - target| >= 2)
- Three semantically equivalent task-spec variants

Scenarios are split into dev (first 18) and held-out (last 6) sets.

V0.3a design principles:
- Scenario metadata (seed, scenario_id, policy_variant, expected action) is
  NEVER included in LLM prompts — experiment-traceability only.
- Each scenario produces a Scenario object compatible with the existing
  worker/oracle/validator pipeline.
- Generator is deterministic: same seed → same scenarios → reproducible results.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

try:
    from .scenario import (
        Action, ActionKind, Episode, Observation, Scenario, TASK_SPEC,
    )
    from .oracle import compute_expected_action
except ImportError:
    from scenario import (
        Action, ActionKind, Episode, Observation, Scenario, TASK_SPEC,
    )
    from oracle import compute_expected_action

__all__ = [
    "ScenarioSpec",
    "generate_scenarios",
    "get_dev_scenarios",
    "get_held_out_scenarios",
    "TASK_SPEC_VARIANTS",
]

# ---------------------------------------------------------------------------
# Task-spec variants (semantically equivalent, syntactically distinct)
# ---------------------------------------------------------------------------

TASK_SPEC_VARIANTS: dict[str, str] = {
    "canonical": TASK_SPEC,
    "variant_b": (
        "Policy: match position_qty to target_signal. When position_qty is "
        "less than target_signal, execute BUY 1. When position_qty exceeds "
        "target_signal, execute SELL 1. When they are equal, execute HOLD. "
        "Respond with exactly one action: BUY 1, SELL 1, or HOLD."
    ),
    "variant_c": (
        "Goal: adjust position_qty until it equals target_signal. If "
        "position_qty < target_signal, buy 1 unit. If position_qty > "
        "target_signal, sell 1 unit. If position_qty == target_signal, "
        "hold. Output precisely one of: BUY 1, SELL 1, HOLD."
    ),
}

# ---------------------------------------------------------------------------
# Scenario specification (intermediate representation)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScenarioSpec:
    """Intermediate specification for a generated scenario.

    Holds the raw parameters before conversion to a Scenario object.
    """
    scenario_id: str
    f_position: int
    l_position: int
    target_signal: int
    f_expected_action: str
    f_expected_qty: int
    l_expected_action: str
    l_expected_qty: int
    corrupt_f: int
    corrupt_l: int
    policy_variant: str
    generator_seed: int


# ---------------------------------------------------------------------------
# Corrupt value computation
# ---------------------------------------------------------------------------

def _compute_corrupt(true_position: int, target_signal: int) -> int:
    """Compute a corrupted position that produces a wrong action.

    Strategy: pick the nearest value that changes the action class.
    - If true action is HOLD (pos == target), use target + 1 (→ SELL)
    - If true action is BUY (pos < target), use target (→ HOLD)
    - If true action is SELL (pos > target), use target (→ HOLD)
    - For negative positions, ensure corrupt stays in valid range.
    """
    if true_position == target_signal:
        # HOLD → corrupt to SELL by adding 1
        return true_position + 1
    elif true_position < target_signal:
        # BUY → corrupt to HOLD by setting to target
        return target_signal
    else:
        # SELL → corrupt to HOLD by setting to target
        return target_signal


# ---------------------------------------------------------------------------
# Scenario matrix (24 curated scenarios)
# ---------------------------------------------------------------------------

# Each tuple: (scenario_id, f_position, l_position, target_signal, policy_variant)
# Expected actions are computed from oracle, not hardcoded.
_SCENARIO_MATRIX: list[tuple[str, int, int, int, str]] = [
    # === Group 1: Non-negative positions, target=0 (S1-like) ===
    ("G1-S01", 0, 1, 0, "canonical"),      # HOLD + SELL
    ("G1-S02", 0, 2, 0, "canonical"),      # HOLD + SELL (multi-unit)
    ("G1-S03", 1, 2, 0, "canonical"),      # SELL + SELL (both above target)

    # === Group 2: Non-negative positions, target=1 ===
    ("G2-S04", 0, 1, 1, "canonical"),      # BUY + HOLD
    ("G2-S05", 0, 2, 1, "canonical"),      # BUY + SELL
    ("G2-S06", 1, 2, 1, "variant_b"),      # HOLD + SELL (variant_b)
    ("G2-S07", 2, 0, 1, "variant_b"),      # SELL + BUY (cross)
    ("G2-S08", 0, 3, 1, "variant_b"),      # BUY + SELL (multi-unit)

    # === Group 3: Non-negative positions, target=2 ===
    ("G3-S09", 1, 2, 2, "variant_c"),      # BUY + HOLD
    ("G3-S10", 2, 3, 2, "variant_c"),      # HOLD + SELL
    ("G3-S11", 1, 3, 2, "variant_c"),      # BUY + SELL
    ("G3-S12", 0, 4, 2, "canonical"),      # BUY + SELL (multi-unit both)

    # === Group 4: Negative positions (short selling) ===
    ("G4-S13", -1, 0, 0, "canonical"),     # SELL + HOLD
    ("G4-S14", -2, 0, 0, "canonical"),     # SELL + HOLD (multi-unit)
    ("G4-S15", -1, 1, 0, "variant_b"),     # SELL + SELL
    ("G4-S16", -2, -1, 0, "variant_b"),    # SELL + SELL (both negative)

    # === Group 5: Negative positions with positive target ===
    ("G5-S17", -1, 0, 1, "variant_c"),     # BUY + BUY (both below)
    ("G5-S18", -1, 1, 1, "variant_c"),     # BUY + HOLD
    ("G5-S19", -2, 0, 1, "canonical"),     # BUY + BUY (multi-unit)
    ("G5-S20", -2, 2, 1, "canonical"),     # BUY + SELL (crosses target)

    # === Group 6: Large multi-unit differences ===
    ("G6-S21", 0, 3, 0, "variant_b"),      # HOLD + SELL (multi-unit)
    ("G6-S22", 3, 0, 3, "variant_b"),      # HOLD + BUY (multi-unit)
    ("G6-S23", -1, 4, 1, "variant_c"),     # BUY + SELL (multi-unit both)
    ("G6-S24", 4, -1, 2, "variant_c"),     # SELL + BUY (multi-unit both, crosses),
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_scenarios(seed: int = 42) -> list[ScenarioSpec]:
    """Generate 24 curated scenario specifications from a seed.

    The seed is used for:
    - Deterministic ordering (though the matrix is fixed)
    - Embedding in scenario metadata for traceability
    - Future: random scenario generation extensions

    Returns a list of ScenarioSpec objects with all metadata populated.
    """
    specs: list[ScenarioSpec] = []
    for idx, (sid, f_pos, l_pos, target, variant) in enumerate(_SCENARIO_MATRIX):
        # Compute expected actions via oracle
        f_action = compute_expected_action(f_pos, target)
        l_action = compute_expected_action(l_pos, target)

        # Compute corrupt positions
        corrupt_f = _compute_corrupt(f_pos, target)
        corrupt_l = _compute_corrupt(l_pos, target)

        # Ensure corrupt values are actually different from true positions
        if corrupt_f == f_pos:
            corrupt_f = f_pos + 1 if f_pos != target + 1 else f_pos - 1
        if corrupt_l == l_pos:
            corrupt_l = l_pos + 1 if l_pos != target + 1 else l_pos - 1

        spec = ScenarioSpec(
            scenario_id=sid,
            f_position=f_pos,
            l_position=l_pos,
            target_signal=target,
            f_expected_action=f_action.kind.value,
            f_expected_qty=f_action.quantity,
            l_expected_action=l_action.kind.value,
            l_expected_qty=l_action.quantity,
            corrupt_f=corrupt_f,
            corrupt_l=corrupt_l,
            policy_variant=variant,
            generator_seed=seed,
        )
        specs.append(spec)
    return specs


def spec_to_scenario(spec: ScenarioSpec) -> Scenario:
    """Convert a ScenarioSpec to a Scenario object.

    The resulting Scenario is compatible with the existing worker/oracle/validator
    pipeline. The policy_variant determines which task_spec is used.
    """
    task_spec = TASK_SPEC_VARIANTS[spec.policy_variant]
    price = 10000
    f_cash = 10000 - spec.f_position * price
    l_cash = 10000 - spec.l_position * price

    f_action = Action(ActionKind[spec.f_expected_action], spec.f_expected_qty)
    l_action = Action(ActionKind[spec.l_expected_action], spec.l_expected_qty)

    initial_ledger = {"cash_cents": 10000, "position_qty": 0}

    observation = Observation(target_signal=spec.target_signal)

    episodes = {
        "F": Episode(
            id="F",
            hidden_position_qty=spec.f_position,
            hidden_cash_cents=f_cash,
            expected_action=f_action,
            expected_ledger=initial_ledger.copy(),
        ),
        "L": Episode(
            id="L",
            hidden_position_qty=spec.l_position,
            hidden_cash_cents=l_cash,
            expected_action=l_action,
            expected_ledger=initial_ledger.copy(),
        ),
    }

    return Scenario(
        version="0.3a",
        seed=spec.generator_seed,
        episodes=episodes,
        observation=observation,
        task_spec=task_spec,
        scenario_id=spec.scenario_id,
    )


def get_dev_scenarios(seed: int = 42) -> list[ScenarioSpec]:
    """Return the development set (first 18 scenarios)."""
    all_specs = generate_scenarios(seed)
    return all_specs[:18]


def get_held_out_scenarios(seed: int = 42) -> list[ScenarioSpec]:
    """Return the held-out test set (last 6 scenarios)."""
    all_specs = generate_scenarios(seed)
    return all_specs[18:]


def scenario_matrix_table() -> str:
    """Return a markdown table of the full scenario matrix."""
    specs = generate_scenarios()
    lines = [
        "| # | Scenario ID | F pos | L pos | Target | F Action | L Action | Corrupt F | Corrupt L | Variant |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(specs, 1):
        lines.append(
            f"| {i} | {s.scenario_id} | {s.f_position} | {s.l_position} "
            f"| {s.target_signal} | {s.f_expected_action}({s.f_expected_qty}) "
            f"| {s.l_expected_action}({s.l_expected_qty}) "
            f"| {s.corrupt_f} | {s.corrupt_l} | {s.policy_variant} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    specs = generate_scenarios()
    print(f"Generated {len(specs)} scenarios")
    print(f"Dev set: {len(get_dev_scenarios())} scenarios")
    print(f"Held-out set: {len(get_held_out_scenarios())} scenarios")
    print()

    # Coverage analysis
    actions_f = set()
    actions_l = set()
    has_negative = False
    has_multi_unit = False
    variants_used = set()
    for s in specs:
        actions_f.add(s.f_expected_action)
        actions_l.add(s.l_expected_action)
        if s.f_position < 0 or s.l_position < 0:
            has_negative = True
        if abs(s.f_position - s.target_signal) >= 2 or abs(s.l_position - s.target_signal) >= 2:
            has_multi_unit = True
        variants_used.add(s.policy_variant)

    print(f"F actions covered: {actions_f}")
    print(f"L actions covered: {actions_l}")
    print(f"Negative positions: {has_negative}")
    print(f"Multi-unit differences: {has_multi_unit}")
    print(f"Policy variants used: {variants_used}")
    print()
    print(scenario_matrix_table())
