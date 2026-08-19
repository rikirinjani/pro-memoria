"""
Fault mutators for PM1 Trading Benchmark v0.1.

Transforms base fixtures into ablation variants. Each starts from a
clean directory — no mutation of corrupt files by appending.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

__all__ = ["mutate_remove_position", "mutate_flip_position", "mutate_restore"]

_PM1_FILES = (
    "project_state.pm1",
    "decisions.pm1",
    "task_records.pm1",
    "worker_reports.pm1",
    "session_log.pm1",
    "historical_trace.pm1",
)


def _load_records(state_dir: str) -> list[dict[str, Any]]:
    """Read all JSON envelopes from the source project-state file."""
    source = Path(state_dir) / "project_state.pm1"
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("project_state.pm1 records must be JSON objects")
            records.append(value)
    if not records:
        raise ValueError("project_state.pm1 contains no records")
    return records


def _write_mutated(records: list[dict[str, Any]]) -> str:
    """Write records into a new clean temporary state directory."""
    directory = Path(tempfile.mkdtemp(prefix="pm1-mutated-"))
    (directory / "project_state.pm1").write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    for filename in _PM1_FILES[1:]:
        (directory / filename).touch()
    return str(directory)


def _latest_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    payload = records[-1].get("payload")
    if not isinstance(payload, dict):
        raise ValueError("latest project-state record has no object payload")
    return payload


def mutate_remove_position(state_dir: str) -> str:
    """Remove position_qty from the latest project_state record."""
    records = _load_records(state_dir)
    _latest_payload(records).pop("position_qty", None)
    return _write_mutated(records)


def mutate_flip_position(state_dir: str) -> str:
    """Flip position_qty (0→1, 1→0) in the latest project_state record."""
    records = _load_records(state_dir)
    payload = _latest_payload(records)
    position = payload.get("position_qty")
    if position not in (0, 1) or isinstance(position, bool):
        raise ValueError("position_qty must be 0 or 1 to flip")
    payload["position_qty"] = 1 - position
    return _write_mutated(records)


def mutate_restore(state_dir: str, correct_position: int) -> str:
    """Create a new clean fixture with correct_position restored."""
    if correct_position not in (0, 1) or isinstance(correct_position, bool):
        raise ValueError("correct_position must be 0 or 1")
    records = _load_records(state_dir)
    _latest_payload(records)["position_qty"] = correct_position
    return _write_mutated(records)


if __name__ == "__main__":
    try:
        from .fixtures import create_b_full
    except ImportError:
        from fixtures import create_b_full

    with tempfile.TemporaryDirectory() as base:
        source = create_b_full(str(Path(base) / "source"), "L")
        variants = (
            mutate_remove_position(source),
            mutate_flip_position(source),
            mutate_restore(mutate_remove_position(source), 1),
        )
        assert "position_qty" not in json.loads(
            (Path(variants[0]) / "project_state.pm1").read_text(encoding="utf-8")
        )["payload"]
        assert json.loads((Path(variants[1]) / "project_state.pm1").read_text(encoding="utf-8"))["payload"]["position_qty"] == 0
        assert json.loads((Path(variants[2]) / "project_state.pm1").read_text(encoding="utf-8"))["payload"]["position_qty"] == 1
    print("mutator: OK")
