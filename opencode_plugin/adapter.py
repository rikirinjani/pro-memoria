"""PM-1 Session Adapter — encode agent session state as PM-1 Morse with failsafe."""

import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent

import sys
sys.path.insert(0, str(MORSE))
from core import encode_bytes, decode_bytes
from dsp import DiffState
from opencode_plugin.failsafe import FailsafePM1, FAILURES_DIR

TRACES_DIR = Path.home() / "self-harness" / "traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)

AGENT_OPS = {
    "orchestrator": 0, "general": 1, "platform": 2, "fixer": 3,
    "explorer": 4, "oracle": 5, "librarian": 6, "coordinator": 7,
    "designer": 8, "paper": 9, "research": 10, "other": 15,
}
OUTCOME_OPS = {"pass": 0, "fail": 1, "partial": 2, "unknown": 3}
SEVERITY_OPS = {"none": 0, "low": 1, "medium": 2, "high": 3}


def trace_to_state(trace: dict) -> bytes:
    """Map a trace dict to an 8-byte state vector (same encoding as benchmark).

    Falls back gracefully for heterogeneous trace schemas (timeline agents,
    session wraps, coordinator handoffs). Fields are required for the 8-byte
    topology encoding; missing fields default to 0/"unknown".
    """
    def bucket(value, ranges):
        for i, threshold in enumerate(ranges):
            if value < threshold:
                return i
        return len(ranges)

    tid = trace.get("trace_id") or trace.get("slug") or "?"
    agent = AGENT_OPS.get(str(trace.get("agent", "other")).lower(), 15)
    outcome = OUTCOME_OPS.get(str(trace.get("outcome", "unknown")).lower(), 3)
    dur = max(trace.get("duration_s", 0) or 0, 0)
    dur_b = bucket(dur, [1, 60, 300, 900, 3600])
    tc = max(trace.get("tool_calls", 0) or 0, 0)
    tc_b = bucket(tc, [1, 10, 30, 100, 300])
    kf = trace.get("key_files", []) or []
    kf_b = bucket(len(kf), [1, 5, 15, 50])
    fail = trace.get("failure", {}) or {}
    cat_map = {"tool": 1, "config": 2, "workflow": 3, "process": 4,
               "communication": 5, "research": 6, "other": 7}
    fail_b = cat_map.get(fail.get("category", "none").lower(), 0) if fail else 0
    sev_b = SEVERITY_OPS.get(fail.get("severity", "none").lower(), 0) if fail else 0
    val_b = 1 if trace.get("validation") else 0
    incomplete = 0 if ("duration_s" in trace and "key_files" in trace) else 1

    return bytes([agent & 0xFF, outcome & 0xFF, dur_b & 0xFF,
                  tc_b & 0xFF, kf_b & 0xFF, fail_b & 0xFF,
                  sev_b & 0xFF, val_b | (incomplete << 1)])


def state_to_trace(state_bytes: bytes, base: dict | None = None) -> dict:
    """Reverse state_to_trace — reconstruct a trace dict from 8-byte state."""
    if len(state_bytes) != 8:
        raise ValueError(f"state must be 8 bytes, got {len(state_bytes)}")
    b = list(state_bytes)
    agent_rev = {v: k for k, v in AGENT_OPS.items()}
    outcome_rev = {v: k for k, v in OUTCOME_OPS.items()}
    validation = bool(b[7] & 0x01)
    incomplete = bool(b[7] & 0x02)
    result = {"agent": agent_rev.get(b[0], "other"),
              "outcome": outcome_rev.get(b[1], "unknown"),
              "duration_s": 0, "tool_calls": 0, "key_files": [],
              "failure": {}, "validation": validation,
              "_incomplete": incomplete}
    if base:
        result.update(base)
    return result


class PM1Session:
    """PM-1 session recorder. Encodes agent steps as Morse, writes traces with failsafe."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now(timezone.utc).strftime("pm1-%Y%m%dT%H%M%S")
        self.failsafe = FailsafePM1(session_id=self.session_id)
        self.dsp = DiffState()
        self.buffer: list[dict] = []
        self.state_buffer: list[bytes] = []
        self.pm1_lines: list[str] = []
        self.prev_state: bytes | None = None

    def record(self, trace: dict) -> str | None:
        """Record a trace step. Returns PM-1 Morse string or hex fallback."""
        state = trace_to_state(trace)
        if state == self.prev_state:
            return None
        encoded = self.failsafe.encode_state(state)
        if encoded is None:
            self.buffer.append(trace)
            return None
        self.state_buffer.append(state)
        self.pm1_lines.append(encoded)
        self.buffer.append(trace)
        self.prev_state = state
        return encoded

    def encode_complete(self) -> str | None:
        """Encode full buffer as combined PM-1 payload. Returns None if failed."""
        if not self.state_buffer:
            return None
        combined = b"".join(self.state_buffer)
        return self.failsafe.encode(combined)

    def flush(self, metadata: dict | None = None) -> Path | None:
        """Write trace file. Uses .pm1 extension if PM-1 encoding succeeded, else .json."""
        slug = self.session_id
        if metadata and metadata.get("slug"):
            slug = metadata["slug"]

        if not self.buffer and not self.state_buffer:
            return None

        combined = self.encode_complete()
        if combined is not None:
            path = TRACES_DIR / f"{slug}.pm1"
            payload = {
                "pm1_version": 1,
                "session_id": self.session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "n_states": len(self.state_buffer),
                "state_width": 8,
                "failsafe": self.failsafe.stats(),
                "metadata": metadata or {},
                "pm1": combined,
            }
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            path = TRACES_DIR / f"{slug}.json"
            fallback = {"trace_id": slug, "failsafe": self.failsafe.stats(),
                        "metadata": metadata or {}, "fallback": True}
            if self.buffer:
                if len(self.buffer) == 1:
                    fallback.update(self.buffer[0])
                else:
                    fallback["entries"] = self.buffer
                path.write_text(json.dumps(fallback, indent=2, ensure_ascii=False))
            else:
                return None

        return path

    def replay(self, path: Path) -> list[dict] | None:
        """Read a .pm1 file back into trace dicts. Returns None on failure."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return None

        if payload.get("pm1_version") != 1 or "pm1" not in payload:
            return None

        data = self.failsafe.decode(payload["pm1"])
        if data is None:
            return None
        if len(data) != payload["n_states"] * payload.get("state_width", 8):
            return None

        traces = []
        for i in range(payload["n_states"]):
            offset = i * payload.get("state_width", 8)
            state = data[offset:offset + payload.get("state_width", 8)]
            base = payload.get("metadata", {}).copy()
            base["step"] = i
            traces.append(state_to_trace(state, base=base))
        return traces

    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "n_records": len(self.buffer),
            "n_states": len(self.state_buffer),
            "failsafe": self.failsafe.stats(),
        }
