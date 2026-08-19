"""
Isolated PM-1 state fixtures for PM1 Trading Benchmark v0.1 / v0.2a / v0.2b / v0.3a.

Creates clean temporary directories with PM-1 record files for each
experimental condition. Each fixture starts from a clean directory —
do not mutate a corrupt file by appending a later valid record.

V0.2a adds B-minus-explicit: same fixture as B-minus (position_qty absent)
but paired with an explicit system-level fail-closed instruction.

V0.2b adds multi-scenario support: S1, S2, S3 with different position values.

V0.3a adds support for generated scenarios via Scenario objects.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

try:
    from .scenario import SCENARIOS, Scenario
except ImportError:
    from scenario import SCENARIOS, Scenario

__all__ = [
    "create_b_full",
    "create_b_minus",
    "create_b_corrupt",
    "create_b_restored",
    "create_state_dir",
]

_PM1_FILES = (
    "project_state.pm1",
    "decisions.pm1",
    "task_records.pm1",
    "worker_reports.pm1",
    "session_log.pm1",
    "historical_trace.pm1",
)


def _position_for_episode(episode_id: str, scenario_id: str = "S1", scenario: Scenario | None = None) -> tuple[int, int]:
    """Return the expected (position_qty, cash_cents) for a benchmark episode.

    V0.2b: Scenario-aware. Cash = 10000 - position_qty * 10000 (price=10000).
    V0.3a: Accepts optional Scenario object for generated scenarios.
    """
    if scenario is not None:
        # V0.3a: Use Scenario object directly
        ep = episode_id.upper()
        if ep == "F":
            pos = scenario.episodes["F"].hidden_position_qty
        elif ep == "L":
            pos = scenario.episodes["L"].hidden_position_qty
        else:
            raise ValueError("episode_id must be 'F' or 'L'")
    else:
        # V0.2b: Look up from SCENARIOS dict
        if scenario_id not in SCENARIOS:
            raise ValueError(f"unknown scenario_id: {scenario_id!r}")
        cfg = SCENARIOS[scenario_id]
        ep = episode_id.upper()
        if ep == "F":
            pos = cfg["f_position"]
        elif ep == "L":
            pos = cfg["l_position"]
        else:
            raise ValueError("episode_id must be 'F' or 'L'")
    cash = 10000 - pos * 10000
    return (pos, cash)


def _corrupt_position(episode_id: str, scenario_id: str = "S1", scenario: Scenario | None = None) -> int:
    """Return the corrupted position_qty for B-corrupt fixture.

    V0.2b: Scenario-aware. The corrupt value is always wrong for the episode.
    V0.3a: Accepts optional Scenario object for generated scenarios.
    """
    if scenario is not None:
        # V0.3a: Compute corrupt from Scenario
        from lib.scenario_generator import _compute_corrupt
        ep = episode_id.upper()
        if ep == "F":
            true_pos = scenario.episodes["F"].hidden_position_qty
        elif ep == "L":
            true_pos = scenario.episodes["L"].hidden_position_qty
        else:
            raise ValueError("episode_id must be 'F' or 'L'")
        return _compute_corrupt(true_pos, scenario.observation.target_signal)
    else:
        # V0.2b: Look up from SCENARIOS dict
        if scenario_id not in SCENARIOS:
            raise ValueError(f"unknown scenario_id: {scenario_id!r}")
        cfg = SCENARIOS[scenario_id]
        ep = episode_id.upper()
        if ep == "F":
            return cfg["corrupt_f"]
        elif ep == "L":
            return cfg["corrupt_l"]
        else:
            raise ValueError("episode_id must be 'F' or 'L'")


def _record(episode_id: str, position_qty: int, scenario_id: str = "S1", scenario: Scenario | None = None) -> dict[str, Any]:
    """Build the single canonical project-state envelope.

    V0.2b: Scenario-aware target_signal.
    V0.3a: Accepts optional Scenario object for generated scenarios.
    """
    if scenario is not None:
        # V0.3a: Use Scenario object directly
        cash_cents = _position_for_episode(episode_id, scenario=scenario)[1]
        target_signal = scenario.observation.target_signal
    else:
        # V0.2b: Look up from SCENARIOS dict
        if scenario_id not in SCENARIOS:
            raise ValueError(f"unknown scenario_id: {scenario_id!r}")
        cfg = SCENARIOS[scenario_id]
        cash_cents = _position_for_episode(episode_id, scenario_id)[1]
        target_signal = cfg["target_signal"]
    return {
        "seq": 1,
        "session_id": "benchmark-fixture",
        "record_type": "project_state",
        "project": "pm1-trading-benchmark",
        "payload": {
            "phase": "trading",
            "project_name": "pm1-trading-benchmark",
            "position_qty": position_qty,
            "cash_cents": cash_cents,
            "instrument": "XYZ",
            "price_cents": 10000,
            "target_signal": target_signal,
            "logical_tick": 1,
            "tags": ["relevant", "trading"],
        },
        "pm1_version": 1,
        "timestamp": "2026-08-14T00:00:00Z",
    }


def _write_fixture(state_dir: Path, record: dict[str, Any]) -> str:
    """Write a clean state directory and return its string path."""
    if state_dir.exists():
        if not state_dir.is_dir() or any(state_dir.iterdir()):
            raise FileExistsError(f"fixture directory is not clean: {state_dir}")
    else:
        state_dir.mkdir(parents=True, exist_ok=False)
    project_state = state_dir / "project_state.pm1"
    project_state.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    for filename in _PM1_FILES[1:]:
        (state_dir / filename).touch()
    return str(state_dir)


def create_state_dir(base_dir: str, variant: str, episode_id: str, scenario_id: str = "S1", scenario: Scenario | None = None) -> str:
    """Create a state directory under *base_dir* for a variant and episode.

    V0.2a: B-minus-explicit creates the same fixture as B-minus
    (position_qty absent). The explicit fail-closed instruction is in
    the system prompt, not the fixture.

    V0.2b: Scenario-aware positions and target_signal. For V0.2b (S1/S2/S3),
    uses SCENARIOS dict for position lookup. For V0.3a (GS001+), uses
    Scenario object directly.
    """
    # V0.2b: Use SCENARIOS dict for S1/S2/S3; V0.3a: Use Scenario object
    if scenario_id in SCENARIOS:
        position_qty, _ = _position_for_episode(episode_id, scenario_id)
    elif scenario is not None:
        position_qty, _ = _position_for_episode(episode_id, scenario=scenario)
    else:
        position_qty, _ = _position_for_episode(episode_id, scenario_id)
    normalized = variant.lower().replace("_", "-")
    if normalized not in {"b-full", "b-minus", "b-minus-explicit", "b-corrupt", "b-restored"}:
        raise ValueError("variant must be B-full, B-minus, B-minus-explicit, B-corrupt, or B-restored")
    if normalized == "b-corrupt":
        if scenario_id in SCENARIOS:
            position_qty = _corrupt_position(episode_id, scenario_id)
        elif scenario is not None:
            position_qty = _corrupt_position(episode_id, scenario=scenario)
        else:
            position_qty = _corrupt_position(episode_id, scenario_id)
    record = _record(episode_id, position_qty, scenario_id, scenario=scenario)
    if normalized in {"b-minus", "b-minus-explicit"}:
        del record["payload"]["position_qty"]
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=f"{normalized}-{episode_id}-", dir=str(base)))
    return _write_fixture(directory, record)


def create_b_full(state_dir: str, episode_id: str, scenario_id: str = "S1") -> str:
    """Create B-full fixture with valid position_qty. Returns state_dir path."""
    return _write_fixture(Path(state_dir), _record(episode_id, _position_for_episode(episode_id, scenario_id)[0], scenario_id))


def create_b_minus(state_dir: str, episode_id: str, scenario_id: str = "S1") -> str:
    """Create B-minus fixture: position_qty is absent from the payload."""
    record = _record(episode_id, _position_for_episode(episode_id, scenario_id)[0], scenario_id)
    del record["payload"]["position_qty"]
    return _write_fixture(Path(state_dir), record)


def create_b_corrupt(state_dir: str, episode_id: str, scenario_id: str = "S1") -> str:
    """Create B-corrupt fixture: position_qty is corrupted (always wrong for the episode)."""
    position_qty = _corrupt_position(episode_id, scenario_id)
    return _write_fixture(Path(state_dir), _record(episode_id, position_qty, scenario_id))


def create_b_restored(state_dir: str, episode_id: str, scenario_id: str = "S1") -> str:
    """Create B-restored fixture with the valid field restored."""
    return _write_fixture(Path(state_dir), _record(episode_id, _position_for_episode(episode_id, scenario_id)[0], scenario_id))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as base:
        for scenario_id in ("S1", "S2", "S3"):
            for episode, expected_pos in (("F", SCENARIOS[scenario_id]["f_position"]), ("L", SCENARIOS[scenario_id]["l_position"])):
                for variant in ("b-full", "b-minus", "b-corrupt", "b-restored"):
                    path = create_state_dir(base, variant, episode, scenario_id)
                    lines = (Path(path) / "project_state.pm1").read_text(encoding="utf-8").splitlines()
                    payload = json.loads(lines[0])["payload"]
                    if variant == "b-minus":
                        assert "position_qty" not in payload
                    else:
                        actual = payload["position_qty"]
                        expected_corrupt = SCENARIOS[scenario_id]["corrupt_" + episode.lower()]
                        assert actual == (expected_corrupt if variant == "b-corrupt" else expected_pos)
                    assert payload["target_signal"] == SCENARIOS[scenario_id]["target_signal"]
                    assert all((Path(path) / name).stat().st_size == 0 for name in _PM1_FILES[1:])
    print("fixtures: OK")
