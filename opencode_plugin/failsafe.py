"""PM-1 Failsafe — auto-detect corruption, auto-rollback, auto-log.

Hamming [8,4,4] is applied at the byte level: each nibble (4 bits) is
encoded as an 8-bit codeword. An 8-byte state becomes 16 Hamming bytes
before Morse encoding. Decoding reverses: Morse -> 16 bytes -> Hamming
verify/correct -> 8 bytes. Single-bit flips are corrected; double-bit
flips are detected as unrecoverable.
"""

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
from hybrid import HybridEncoder, ENCODING_MORSE, ENCODING_BRAILLE
from lexicon import hamming_encode, hamming_decode

FAILURES_DIR.mkdir(parents=True, exist_ok=True)

# Precompute Hamming codewords for all 16 nibble values
_NIBBLE_TO_HAMMING = [hamming_encode(i) for i in range(16)]


def _hamming_protect(data: bytes) -> bytes:
    """8-byte state -> 16-byte Hamming [8,4,4] protected."""
    result = bytearray()
    for b in data:
        result.append(_NIBBLE_TO_HAMMING[(b >> 4) & 0x0F])
        result.append(_NIBBLE_TO_HAMMING[b & 0x0F])
    return bytes(result)


def _hamming_verify(data: bytes) -> tuple[bytes | None, bool, int]:
    """16-byte Hamming data -> (8-byte state | None, unrecoverable, n_corrected)."""
    if len(data) % 16 != 0:
        return None, True, 0
    result = bytearray()
    corrected = 0
    for i in range(0, len(data), 2):
        upper, corr_u, err_u = hamming_decode(data[i])
        if err_u:
            return None, True, 0
        if corr_u:
            corrected += 1
        lower, corr_l, err_l = hamming_decode(data[i + 1])
        if err_l:
            return None, True, 0
        if corr_l:
            corrected += 1
        nib = ((upper & 0x0F) << 4) | (lower & 0x0F)
        result.append(nib)
    return bytes(result), False, corrected


class FailsafePM1:
    """Wraps PM-1 encode/decode with Hamming ECC and auto-regress.

    State machine:
        ACTIVE -> (on >30% errors) -> DISABLED
        DISABLED: all calls return None (JSON/hex passthrough).
    """

    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"

    def __init__(self, session_id: str | None = None, encoding: str = ENCODING_MORSE):
        self.session_id = session_id or f"pm1-{int(time.time())}"
        self.encoder = HybridEncoder(encoding)
        self.status = self.ACTIVE
        self.error_window = []
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
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        self.failure_ids.append(record["trace_id"])
        self.last_error = record
        return record

    def encode(self, data: bytes) -> str | None:
        """Encode bytes with Hamming protection then Morse.

        Returns None on failure (caller falls through to JSON/hex).
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
                "data_hex": data.hex(), "data_len": len(data),
                "error": f"state width must be multiple of 8, got {len(data)}",
            })
            self._check_disable()
            return None

        try:
            protected = _hamming_protect(data)
            encoded = self.encoder.encode_bytes(protected)
            decoded_protected = self.encoder.decode_str(encoded)
            if decoded_protected != protected:
                raise ValueError(f"roundtrip mismatch at byte level")
            recovered, unrecoverable, n_corrected = _hamming_verify(decoded_protected)
            if unrecoverable or recovered is None:
                raise ValueError("Hamming unrecoverable on freshly encoded data")
            if recovered != data:
                raise ValueError(f"Hamming roundtrip mismatch: {data.hex()} -> {recovered.hex()}")
            self.total_corrected += n_corrected
            self.error_window.append(False)
            if len(self.error_window) > self.window_size:
                self.error_window.pop(0)
            return encoded
        except Exception as e:
            self.total_errors += 1
            self.error_window.append(True)
            if len(self.error_window) > self.window_size:
                self.error_window.pop(0)
            err_type = "hamming_unrecoverable" if "unrecoverable" in str(e) else "corrupted_state"
            self._record_failure(err_type, {
                "data_hex": data.hex(), "data_len": len(data), "error": str(e),
            })
            self._check_disable()
            return None

    def _check_disable(self):
        if self.error_rate > 0.3 and len(self.error_window) >= self.window_size:
            self.status = self.DISABLED

    def encode_state(self, state_bytes: bytes) -> str | None:
        """Encode a single 8-byte state. Falls through to hex on failure."""
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
            "state_hex": state_bytes.hex(), "reason": "PM-1 ECC encode failed",
        })
        return h

    def decode(self, encoded: str) -> bytes | None:
        """Decode an encoded string back through Hamming verify.

        Returns corrected bytes, or None on unrecoverable corruption.
        """
        try:
            protected = self.encoder.decode_str(encoded)
            recovered, unrecoverable, n_corrected = _hamming_verify(protected)
            if unrecoverable:
                self._record_failure("hamming_unrecoverable", {
                    "encoded": encoded[:40], "reason": "double-bit error, cannot recover",
                })
                return None
            if n_corrected > 0:
                self.total_corrected += n_corrected
                self._record_failure("hamming_corrected", {
                    "encoded": encoded[:40], "n_corrected": n_corrected,
                })
            return recovered
        except Exception as e:
            self._record_failure("invalid_encoding", {
                "encoded": encoded[:40], "error": str(e),
            })
            return None

    def decode_state(self, encoded: str) -> bytes | None:
        """Decode a state from encoded form or hex fallback."""
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

    @staticmethod
    def flip_nth_morse_char(morse: str, n: int) -> str:
        chars = list(morse)
        orig = chars[n]
        chars[n] = "." if orig == "-" else "-"
        return "".join(chars)
