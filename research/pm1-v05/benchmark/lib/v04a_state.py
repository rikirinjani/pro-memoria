"""
PM-1 handoff state representation for PM1 Trading Benchmark v0.4a.

Defines the semantic state carried across sequential worker handoffs, the
PM-1 encode/decode path (matching the canonical sections->records->payload
packet shape used by the context assembler in V0.1-V0.3a), a plain-text
direct-state encoding for the H-direct control condition, and a semantic
state digest that is independent of chain ID, hop number, trial, and run ID.

The digest covers ONLY the semantic state fields (position_qty,
target_signal) so that digest continuity measures semantic state, not
experiment identity.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

__all__ = [
    "State",
    "encode_pm1_state",
    "decode_pm1_state",
    "encode_direct_state",
    "decode_direct_state",
    "state_digest",
    "STATE_FIELDS",
]

STATE_FIELDS = ("position_qty", "target_signal")

_PRICE_CENTS = 10000
_INSTRUMENT = "XYZ"


@dataclass(frozen=True)
class State:
    """Semantic state carried across a handoff."""

    position_qty: int
    target_signal: int
    cash_cents: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "position_qty": self.position_qty,
            "target_signal": self.target_signal,
            "cash_cents": self.cash_cents,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "State":
        return cls(
            position_qty=int(data["position_qty"]),
            target_signal=int(data["target_signal"]),
            cash_cents=int(data.get("cash_cents", 0)),
        )


def _payload(position_qty: int, target_signal: int, cash_cents: int, tick: int = 1) -> dict[str, Any]:
    """Build the canonical project-state payload (matches fixtures._record)."""
    return {
        "phase": "trading",
        "project_name": "pm1-trading-benchmark",
        "position_qty": position_qty,
        "cash_cents": cash_cents,
        "instrument": _INSTRUMENT,
        "price_cents": _PRICE_CENTS,
        "target_signal": target_signal,
        "logical_tick": tick,
        "tags": ["relevant", "trading"],
    }


def encode_pm1_state(state: State, tick: int = 1) -> dict[str, Any]:
    """Encode a State into the canonical PM-1 assembled packet.

    Returns a dict with the same sections->records->payload shape that the
    context assembler produces, so the H-full condition exercises the real
    PM-1 representation.
    """
    return {
        "sections": [
            {
                "title": "project_state",
                "records": [
                    {
                        "record_type": "project_state",
                        "payload": _payload(state.position_qty, state.target_signal, state.cash_cents, tick),
                    }
                ],
            }
        ]
    }


def decode_pm1_state(packet: dict[str, Any]) -> State:
    """Decode a PM-1 packet back into a State.

    Raises
    ------
    ValueError
        If the packet does not contain a valid position_qty / target_signal.
    """
    if not isinstance(packet, dict):
        raise ValueError(f"PM-1 packet must be a dict, got {type(packet).__name__}")
    for section in packet.get("sections", []):
        for record in section.get("records", []):
            payload = record.get("payload", {})
            if "position_qty" in payload:
                position = payload["position_qty"]
                target = payload.get("target_signal", 0)
                cash = payload.get("cash_cents", 0)
                if isinstance(position, bool) or not isinstance(position, int):
                    raise ValueError(f"invalid position_qty in packet: {position!r}")
                return State(position_qty=position, target_signal=int(target), cash_cents=int(cash))
    raise ValueError("PM-1 packet does not contain position_qty")


def encode_direct_state(state: State) -> str:
    """Encode a State as plain text for the H-direct control condition."""
    return (
        f"position_qty = {state.position_qty}\n"
        f"target_signal = {state.target_signal}"
    )


def decode_direct_state(text: str) -> State:
    """Decode a plain-text direct state (H-direct control)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("direct state is empty")
    values: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if key not in STATE_FIELDS:
            continue
        try:
            values[key] = int(raw.strip())
        except (ValueError, TypeError):
            raise ValueError(f"invalid direct-state value for {key!r}: {raw!r}")
    if "position_qty" not in values:
        raise ValueError("direct state is missing position_qty")
    target = values.get("target_signal", 0)
    return State(position_qty=values["position_qty"], target_signal=target)


def state_digest(state: State) -> str:
    """Return a semantic state digest.

    Computed over ONLY position_qty and target_signal (canonical JSON), so
    the digest is invariant to chain ID, hop number, trial, run ID, and any
    non-semantic envelope fields.
    """
    canonical = json.dumps(
        {"position_qty": state.position_qty, "target_signal": state.target_signal},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
