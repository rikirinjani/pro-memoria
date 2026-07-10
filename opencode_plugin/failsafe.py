"""PM-1 Failsafe — auto-detect corruption, auto-rollback, auto-log."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
FAILURES_DIR = Path.home() / "self-harness" / "failures"

import sys
sys.path.insert(0, str(MORSE))
import core

FAILURES_DIR.mkdir(parents=True, exist_ok=True)

CORRUPTION_HEADERS = (
    "corrupted_state", "roundtrip_mismatch", "hamming_unrecoverable",
    "invalid_morse_char", "length_mismatch",
)

class FailsafePM1:
    """Wraps PM-1 encode/decode with roundtrip verification and auto-regress.

    State machine:
        ACTIVE  → (on error) → DEGRADED → (on >30% errors) → DISABLED
        DISABLED: all calls fall through to JSON passthrough, no PM-1 encoding.
    """

    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f"pm1-{int(time.time())}"
        self.status = self.ACTIVE
        self.error_window = []  # rolling window of last N bools (True=error)
        self.window_size = 10
        self.total_encodes = 0
        self.total_errors = 0
        self.total_corrected = 0
        self.fallback_count = 0
        self.last_error = None
        self.failure_ids = []

    @property
    def error_rate(self) -> float:
        if not self.error_window:
            return 0.0
        return sum(self.error_window) / len(self.error_window)

    def _record_failure(self, error_type: str, details: dict):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%z")
        slug = f"pm1-failsafe-{error_type}-{ts}"
        record = {
            "trace_id": f"pm1-failsafe-{ts}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": "process",
            "severity": "low" if error_type == "hamming_corrected" else "medium",
            "agent": "opencode",
            "slug": slug,
            "error_type": error_type,
            "session_id": self.session_id,
            "details": details,
        }
        path = FAILURES_DIR / f"{ts}-{error_type}-{slug[:40]}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        self.failure_ids.append(record["trace_id"])
        self.last_error = record
        return record

    def encode(self, data: bytes) -> str | None:
        """Encode bytes to PM-1 Morse. Requires state width to be multiple of 8 bytes.

        Returns None on unrecoverable failure (falls through to JSON/hex).
        Auto-regresses if error rate > 30% in rolling window.
        """
        self.total_encodes += 1
        if self.status == self.DISABLED:
            return None

        if len(data) % 8 != 0:
            self.total_errors += 1
            self.error_window.append(True)
            if len(self.error_window) > self.window_size:
                self.error_window.pop(0)
            self._record_failure("invalid_state_width", {
                "data_len": len(data),
                "error": f"state width must be multiple of 8, got {len(data)}",
            })
            if self.error_rate > 0.3 and len(self.error_window) >= self.window_size:
                self.status = self.DISABLED
            return None

        try:
            morse = core.encode_bytes(data)
            decoded = core.decode_bytes(morse)
            if decoded != data:
                raise ValueError(f"roundtrip mismatch: {data.hex()}: {morse} -> {decoded.hex()}")
            self.error_window.append(False)
            if len(self.error_window) > self.window_size:
                self.error_window.pop(0)
            return morse
        except Exception as e:
            self.total_errors += 1
            self.error_window.append(True)
            if len(self.error_window) > self.window_size:
                self.error_window.pop(0)
            err_type = "roundtrip_mismatch" if "roundtrip" in str(e) else "corrupted_state"
            self._record_failure(err_type, {
                "data_hex": data.hex(),
                "data_len": len(data),
                "error": str(e),
            })
            if self.error_rate > 0.3 and len(self.error_window) >= self.window_size:
                self.status = self.DISABLED
            return None

    def encode_state(self, state_bytes: bytes) -> str | None:
        """Encode a single 8-byte state vector. Falls through to hex on failure."""
        result = self.encode(state_bytes)
        if result is not None:
            return result
        if self.status == self.DISABLED:
            return None
        self.fallback_count += 1
        if state_bytes is None or len(state_bytes) != 8:
            return None
        h = state_bytes.hex()
        self._record_failure("fallback_to_hex", {
            "state_hex": state_bytes.hex(),
            "reason": "PM-1 encode failed",
        })
        return h

    def decode(self, morse: str) -> bytes | None:
        """Decode PM-1 Morse back to bytes. Returns None if unrecoverable."""
        try:
            data = core.decode_bytes(morse)
            return data
        except Exception as e:
            self._record_failure("invalid_morse_char", {
                "morse": morse[:40],
                "error": str(e),
            })
            return None

    def decode_state(self, encoded: str) -> bytes | None:
        """Decode a state from PM-1 Morse or hex fallback."""
        if len(encoded) == 16 and all(c in "0123456789abcdef" for c in encoded.lower()):
            return bytes.fromhex(encoded)
        return self.decode(encoded)

    def reset(self):
        self.status = self.ACTIVE
        self.error_window.clear()
        self.total_encodes = 0
        self.total_errors = 0
        self.total_corrected = 0
        self.fallback_count = 0

    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "total_encodes": self.total_encodes,
            "total_errors": self.total_errors,
            "total_corrected": self.total_corrected,
            "fallback_count": self.fallback_count,
            "error_rate_rolling": round(self.error_rate, 3),
            "failure_ids": self.failure_ids,
        }


class CorruptedMorse:
    """Simulate and detect corruption — for failsafe testing."""

    @staticmethod
    def flip_bit(morse: str, bit_index: int) -> str:
        chars = list(morse)
        if chars[bit_index] == ".":
            chars[bit_index] = "-"
        else:
            chars[bit_index] = "."
        return "".join(chars)


