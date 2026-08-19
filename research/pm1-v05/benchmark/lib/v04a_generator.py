"""
Deterministic chain generation for PM1 Trading Benchmark v0.4a.

Produces independent chains, each with:
- chain_id
- generator_seed
- initial_state
- target_schedule (per-hop target_signal, length = hops)
- corruption schedule (hops where H-corrupt injects corruption)
- restoration schedule (hops where H-recover restores the oracle state)
- scenario_metadata

Generation is fully deterministic (no uncontrolled randomness). The 10-chain
pool covers HOLD/BUY/SELL-producing states, zero/positive/negative positions,
multi-unit position differences, and target changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from lib.v04a_state import State

__all__ = [
    "ChainSpec",
    "generate_chain_specs",
    "generate_single_chain_spec",
    "INITIAL_STATE_POOL",
    "CHAIN_COUNT",
    "HOPS",
]

CHAIN_COUNT = 10
HOPS = 100

# Curated pool of diverse initial configurations (one per chain).
# Each entry: (position_qty, target_signal, label) covering:
#   HOLD / BUY / SELL-producing states, zero/positive/negative positions,
#   multi-unit position differences (|pos - target| >= 2).
INITIAL_STATE_POOL: list[tuple[int, int, str]] = [
    (0, 0, "HOLD zero"),
    (0, 1, "BUY zero"),
    (2, 0, "SELL positive multi-unit"),
    (1, 2, "BUY positive"),
    (-1, 0, "BUY negative"),
    (-3, 1, "BUY negative multi-unit"),
    (3, 1, "SELL positive multi-unit"),
    (0, 3, "BUY zero multi-unit"),
    (-2, 1, "BUY negative multi-unit"),
    (4, 2, "SELL positive multi-unit"),
]

_PRICE_CENTS = 10000


def _cash(position_qty: int) -> int:
    return 10000 - position_qty * _PRICE_CENTS


def _target_schedule(seed: int, hops: int, base_target: int) -> tuple[int, ...]:
    """Deterministic per-hop target schedule.

    The target changes at deterministic boundaries (every 33 hops) to ensure
    the chain is not a single fixed target for the whole run — otherwise the
    trajectory would converge to HOLD and hide drift.
    """
    anchors = [base_target]
    state = seed & 0xFFFFFFFF
    for _ in range(3):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        shift = (state >> 16) % 5
        # Keep targets in a small band but change them deterministically.
        anchor = (anchors[-1] + shift - 2) % 4
        anchors.append(anchor)

    schedule: list[int] = []
    boundaries = [0, hops // 3, (2 * hops) // 3, hops]
    for i in range(hops):
        idx = next((k for k in range(3) if boundaries[k] <= i < boundaries[k + 1]), 3)
        schedule.append(anchors[idx])
    return tuple(schedule)


def _deterministic_hops(seed: int, count: int, modulo: int, offset: int = 0) -> tuple[int, ...]:
    """Deterministic 1-indexed hop numbers for corruption/restoration."""
    state = seed & 0xFFFFFFFF
    hops: list[int] = []
    for _ in range(count):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        hop = offset + (state >> 16) % modulo + 1
        # Avoid duplicates
        while hop in hops or hop <= 0:
            state = (state * 1103515245 + 12345) & 0xFFFFFFFF
            hop = offset + (state >> 16) % modulo + 1
        hops.append(hop)
    return tuple(sorted(hops))


@dataclass(frozen=True)
class ChainSpec:
    """Deterministic specification of one V0.4a chain."""

    chain_id: str
    generator_seed: int
    initial_state: State
    target_schedule: tuple[int, ...]
    corrupt_hops: tuple[int, ...] = ()
    restore_hops: tuple[int, ...] = ()
    scenario_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def hops(self) -> int:
        return len(self.target_schedule)

    def state_at(self, hop: int) -> State:
        """Semantic state a perfect worker should hold at 1-indexed hop."""
        target = self.target_schedule[hop - 1]
        return State(position_qty=self.initial_state.position_qty, target_signal=target)

    def target_at(self, hop: int) -> int:
        return self.target_schedule[hop - 1]


def _chain_seed(chain_index: int, base_seed: int) -> int:
    digest = hashlib.sha256(f"v04a:{base_seed}:{chain_index}".encode()).hexdigest()
    return int(digest[:8], 16)


def generate_single_chain_spec(
    chain_index: int,
    base_seed: int = 42,
    hops: int = HOPS,
    chain_count: int = CHAIN_COUNT,
) -> ChainSpec:
    """Generate one deterministic chain spec by index (1-based)."""
    if not 1 <= chain_index <= chain_count:
        raise ValueError(f"chain_index must be 1..{chain_count}, got {chain_index}")
    seed = _chain_seed(chain_index, base_seed)
    position, target, label = INITIAL_STATE_POOL[chain_index - 1]
    initial = State(position_qty=position, target_signal=target, cash_cents=_cash(position))
    schedule = _target_schedule(seed, hops, target)
    # Corruption at deterministic interior hops (never hop 1, never hop 100).
    corrupt = _deterministic_hops(seed, 2, max(2, hops // 3), offset=max(1, hops // 4))
    corrupt = tuple(h for h in corrupt if 1 < h < hops)[:2]
    # Restore: the hop immediately after each corruption hop.
    restore = tuple(h + 1 for h in corrupt if h + 1 <= hops)
    return ChainSpec(
        chain_id=f"chain-{chain_index:02d}",
        generator_seed=seed,
        initial_state=initial,
        target_schedule=schedule,
        corrupt_hops=corrupt,
        restore_hops=restore,
        scenario_metadata={
            "label": label,
            "base_seed": base_seed,
            "hops": hops,
            "chain_index": chain_index,
        },
    )


def generate_chain_specs(
    base_seed: int = 42,
    chains: int = CHAIN_COUNT,
    hops: int = HOPS,
) -> list[ChainSpec]:
    """Generate all chain specs deterministically."""
    return [generate_single_chain_spec(i, base_seed, hops, chains) for i in range(1, chains + 1)]


def diversity_report(specs: list[ChainSpec]) -> dict[str, Any]:
    """Summarize scenario diversity across the generated chains."""
    actions = {"HOLD": 0, "BUY": 0, "SELL": 0}
    zero = positive = negative = 0
    multi_unit = 0
    target_changes = 0
    for spec in specs:
        pos = spec.initial_state.position_qty
        tgt = spec.initial_state.target_signal
        if pos < tgt:
            actions["BUY"] += 1
        elif pos > tgt:
            actions["SELL"] += 1
        else:
            actions["HOLD"] += 1
        if pos == 0:
            zero += 1
        elif pos > 0:
            positive += 1
        else:
            negative += 1
        if abs(pos - tgt) >= 2:
            multi_unit += 1
        uniq = set(spec.target_schedule)
        if len(uniq) > 1:
            target_changes += 1
    return {
        "chains": len(specs),
        "initial_action_coverage": actions,
        "zero_positions": zero,
        "positive_positions": positive,
        "negative_positions": negative,
        "multi_unit_diffs": multi_unit,
        "chains_with_target_changes": target_changes,
    }


if __name__ == "__main__":
    specs = generate_chain_specs()
    print(f"Generated {len(specs)} chains x {specs[0].hops} hops")
    print(diversity_report(specs))
