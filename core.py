"""Pro Memoria — Core Protocol Phase 1: bits <-> Morse encoding.

ASCII-native binary encoding for AI agent state communication.
. = 0  (dot)
- = 1  (dash)

Design properties:
- 8 fixed-length chars per byte (MSB-first)
- Deterministic, roundtrip-safe for all 256 byte values
- Zero dependencies, pure Python 3
- ASCII . and - are always 1 token per character in every tokenizer
"""


def bits_to_morse(byte: int) -> str:
    """Encode a byte (0-255) as an 8-character Morse string.

    >>> bits_to_morse(0x41)
    '.-.....-'
    >>> bits_to_morse(0xC0)
    '--......'
    >>> bits_to_morse(0x00)
    '........'
    >>> bits_to_morse(0xFF)
    '--------'
    """
    if not (0 <= byte <= 255):
        raise ValueError(f"byte must be 0-255, got {byte}")
    return ''.join('-' if (byte >> (7 - i)) & 1 else '.' for i in range(8))


def morse_to_bits(morse: str) -> int:
    """Decode an 8-character Morse string back to a byte.

    >>> morse_to_bits('.-.....-')
    65
    >>> morse_to_bits('--......')
    192
    >>> morse_to_bits('........')
    0
    >>> morse_to_bits('--------')
    255
    """
    if len(morse) != 8:
        raise ValueError(f"morse string must be exactly 8 chars, got {len(morse)}")
    result = 0
    for i, ch in enumerate(morse):
        if ch == '-':
            result |= 1 << (7 - i)
        elif ch == '.':
            pass
        else:
            raise ValueError(f"invalid morse character: {repr(ch)}")
    return result


def roundtrip_check() -> bool:
    """Verify bits_to_morse -> morse_to_bits for all 256 bytes."""
    for b in range(256):
        encoded = bits_to_morse(b)
        decoded = morse_to_bits(encoded)
        if decoded != b:
            return False
    return True


def encode_bytes(data: bytes) -> str:
    """Encode a bytes object to a Morse string sequence.

    >>> encode_bytes(b'Hi')
    '.-..-....--.-..-'
    """
    return ''.join(bits_to_morse(b) for b in data)


def decode_bytes(morse: str) -> bytes:
    """Decode a Morse string sequence back to bytes.

    >>> decode_bytes('.-..-....--.-..-')
    b'Hi'
    """
    if len(morse) % 8 != 0:
        raise ValueError(f"morse string length must be multiple of 8, got {len(morse)}")
    return bytes(morse_to_bits(morse[i:i+8]) for i in range(0, len(morse), 8))


if __name__ == '__main__':
    ok = roundtrip_check()
    print(f"Roundtrip 0-255: {'PASS' if ok else 'FAIL'}")

    import doctest
    results = doctest.testmod(verbose=False)
    print(f"Doctests: {results.attempted} attempted, {results.failed} failed")
