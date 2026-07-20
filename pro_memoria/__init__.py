"""Pro Memoria (PM-1) — single-agent state telemetry protocol.

Encodes 8-bit binary state as ASCII Morse (`.` for 0, `-` for 1)
with differential emission, Hamming error correction, and handshake recovery.
Zero-dependency Python 3.

Quick start:
    >>> from pro_memoria import bits_to_morse
    >>> bits_to_morse(0x41)
    '.-.....-'
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── Phase 1: Core bits <-> Morse ──────────────────────────────────────
from core import bits_to_morse, morse_to_bits, encode_bytes, decode_bytes

# ── Phase 2: Differential State Protocol ──────────────────────────────
from dsp import DiffState, encode_diff, decode_diff

# ── Phase 3: Lexicon (Hamming + Parity commands) ──────────────────────
from lexicon import hamming_encode, hamming_decode, parity_encode, parity_decode

# ── Hybrid encoder (Morse / Braille) ──────────────────────────────────
from hybrid import ENCODING_MORSE, ENCODING_BRAILLE, HybridEncoder

__all__ = [
    # core
    "bits_to_morse", "morse_to_bits", "encode_bytes", "decode_bytes",
    # dsp
    "DiffState", "encode_diff", "decode_diff",
    # lexicon
    "hamming_encode", "hamming_decode", "parity_encode", "parity_decode",
    # hybrid
    "ENCODING_MORSE", "ENCODING_BRAILLE", "HybridEncoder",
]
