"""Tests for hybrid PM-1 / AB-1 encoder."""

from hybrid import HybridEncoder, ENCODING_MORSE, ENCODING_BRAILLE, _braille_encode_byte, _braille_decode_char, _morse_encode_byte


def test_default_encoding_is_morse():
    enc = HybridEncoder()
    assert enc.encoding == ENCODING_MORSE, "Default should be PM-1 Morse"


def test_morse_roundtrip_all_bytes():
    enc = HybridEncoder(ENCODING_MORSE)
    for b in range(256):
        c = enc.encode_byte(b)
        assert len(c) == 8, f"Morse should be 8 chars at b={b}"
        assert enc.decode_char(c) == b, f"Roundtrip failed at b={b}"
    print(f"  [PASS] Morse roundtrip: 256/256")


def test_braille_roundtrip_all_bytes():
    enc = HybridEncoder(ENCODING_BRAILLE)
    for b in range(256):
        c = enc.encode_byte(b)
        assert 0x2800 <= ord(c) <= 0x28FF, f"Braille out of range at b={b}"
        assert enc.decode_char(c) == b, f"Roundtrip failed at b={b}"
    print(f"  [PASS] Braille roundtrip: 256/256")


def test_braille_independent():
    """Verify pure arithmetic Braille works without external dependency."""
    for b in range(256):
        c = _braille_encode_byte(b)
        out = _braille_decode_char(c)
        assert out == b, f"Braille math failed at b={b}"
    print(f"  [PASS] Braille independent math: 256/256")


def test_negotiation():
    enc = HybridEncoder()
    assert enc.encoding == ENCODING_MORSE

    # Peer supports only Morse -> stays Morse
    result = enc.negotiate({ENCODING_MORSE})
    assert result == ENCODING_MORSE
    assert enc.encoding == ENCODING_MORSE

    # Peer supports both -> upgrades to Braille
    result = enc.negotiate({ENCODING_MORSE, ENCODING_BRAILLE})
    assert result == ENCODING_BRAILLE
    assert enc.encoding == ENCODING_BRAILLE

    print("  [PASS] Negotiation: Morse only stays Morse, both upgrades to Braille")


def test_upgrade_and_reset():
    enc = HybridEncoder()
    assert enc.encoding == ENCODING_MORSE
    enc.upgrade_to(ENCODING_BRAILLE)
    assert enc.encoding == ENCODING_BRAILLE

    # Test Braille encode after upgrade
    assert enc.encode_byte(0x41) == chr(0x2841)

    # Reset back to Morse on error recovery
    enc.reset()
    assert enc.encoding == ENCODING_MORSE
    assert enc.encode_byte(0x41) == _morse_encode_byte(0x41)

    print("  [PASS] Upgrade and reset")


def test_cross_encoding_same_value():
    """Both encodings must encode the same byte value."""
    morse = HybridEncoder(ENCODING_MORSE)
    braille = HybridEncoder(ENCODING_BRAILLE)
    for b in [0x00, 0x41, 0xFF, 0x80, 0x01]:
        mc = morse.decode_char(morse.encode_byte(b))
        bc = braille.decode_char(braille.encode_byte(b))
        assert mc == bc == b, f"Cross-encoding mismatch at b={b}"
    print("  [PASS] Cross-encoding match")


def test_invalid_encoding_raises():
    try:
        HybridEncoder("base64")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    try:
        enc = HybridEncoder()
        enc.upgrade_to("hex")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] Invalid encoding raises ValueError")


def test_byte_out_of_range():
    enc = HybridEncoder()
    try:
        enc.encode_byte(256)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] Out-of-range byte raises ValueError")


def main():
    print("=" * 50)
    print("  Hybrid PM-1 / AB-1 Encoder Tests")
    print("=" * 50)
    tests = [
        test_default_encoding_is_morse,
        test_morse_roundtrip_all_bytes,
        test_braille_roundtrip_all_bytes,
        test_braille_independent,
        test_negotiation,
        test_upgrade_and_reset,
        test_cross_encoding_same_value,
        test_invalid_encoding_raises,
        test_byte_out_of_range,
    ]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    verdict = "PASS" if failed == 0 else "FAIL"
    print(f"  OVERALL: [{verdict}]")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
