"""Hybrid PM-1 / AB-1 encoder — starts with Morse, upgrades to Braille on capability match.

PM-1 Morse is the universal baseline (zero setup required everywhere).
AB-1 Braille is the optional density upgrade (requires tokenizer extension).

The handshake negotiates encoding: Morse → ENCODING/ENCODING_ACK → Braille.
If both sides understand Braille, ongoing DATA uses Braille cells (~20% denser).
If not, Morse is always available — no silent fragmentation.
"""

from protocol import ENCODING_MORSE, ENCODING_BRAILLE, SUPPORTED_ENCODINGS


class HybridEncoder:
    """Per-byte encoder that transparently switches between Morse and Braille.

    Defaults to PM-1 Morse. Call upgrade() after ENCODING_ACK to switch.
    No dependencies on the AB-1 package — Braille encoding is pure arithmetic
    (byte → U+2800+byte, decode → ord(cell) - 0x2800).
    """

    def __init__(self, encoding: str = ENCODING_MORSE):
        if encoding not in SUPPORTED_ENCODINGS:
            raise ValueError(f"Unsupported encoding: {encoding}. "
                             f"Supported: {sorted(SUPPORTED_ENCODINGS)}")
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        return self._encoding

    def encode_byte(self, b: int) -> str:
        """Encode a single byte (0-255) to the current encoding."""
        if not 0 <= b <= 255:
            raise ValueError(f"Byte value out of range: {b}")
        if self._encoding == ENCODING_MORSE:
            return _morse_encode_byte(b)
        return chr(0x2800 + b)

    def decode_char(self, c: str) -> int:
        """Decode a single character back to a byte."""
        if self._encoding == ENCODING_MORSE:
            return _morse_decode_char(c)
        return ord(c) - 0x2800

    def negotiate(self, peer_encodings: set[str]) -> str:
        """Select best encoding based on peer capabilities.

        Always agrees on some encoding — never returns None.
        Priority: Braille > Morse (density wins when both sides support it).
        """
        available = SUPPORTED_ENCODINGS & peer_encodings
        if ENCODING_BRAILLE in available:
            self._encoding = ENCODING_BRAILLE
        else:
            self._encoding = ENCODING_MORSE
        return self._encoding

    def upgrade_to(self, encoding: str) -> None:
        """Force encoding switch (call after ENCODING_ACK)."""
        if encoding not in SUPPORTED_ENCODINGS:
            raise ValueError(f"Cannot upgrade to unsupported encoding: {encoding}")
        self._encoding = encoding

    def reset(self) -> None:
        """Reset to Morse (default) — e.g. on error recovery."""
        self._encoding = ENCODING_MORSE


# ── Fast encode/decode helpers (no lexicon/core import needed) ──────

_MORSE_TABLE: dict[int, str] = {}
_MORSE_REV: dict[str, int] = {}
for b in range(256):
    chars = []
    for bit in range(7, -1, -1):
        chars.append("-" if (b >> bit) & 1 else ".")
    s = "".join(chars)
    _MORSE_TABLE[b] = s
    _MORSE_REV[s] = b


def _morse_encode_byte(b: int) -> str:
    return _MORSE_TABLE[b]


def _morse_decode_char(c: str) -> int:
    return _MORSE_REV[c]


def _braille_encode_byte(b: int) -> str:
    return chr(0x2800 + b)


def _braille_decode_char(c: str) -> int:
    return ord(c) - 0x2800
