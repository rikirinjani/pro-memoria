"""Integration tests for PM-1 Hybrid Handshake + Hybrid DSP + Failsafe."""

from handshake import HybridHandshake, HandshakeError
from hybrid import ENCODING_MORSE, ENCODING_BRAILLE
from dsp import DiffState
from opencode_plugin.failsafe import FailsafePM1


PASS = "PASS"
FAIL = "FAIL"

results = []


def check(name: str, status: str, detail: str = ""):
    results.append({"test": name, "status": status, "detail": detail})
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))


# ── Handshake tests ───────────────────────────────────────────────────

def test_hs1_initiator_upgrades_to_braille():
    hs = HybridHandshake()
    cmds = hs.full_handshake_initiator('morse,braille')
    check("initiator_braille_upgrade", PASS if hs.encoder.encoding == ENCODING_BRAILLE else FAIL,
          f"encoding={hs.encoder.encoding}")
    assert 'HELLO' in cmds and 'ENCODING_ACK braille' in cmds and 'ACK' in cmds


def test_hs2_morse_only_peer():
    hs = HybridHandshake()
    hs.full_handshake_initiator('morse')
    check("morse_only_peer", PASS if hs.encoder.encoding == ENCODING_MORSE else FAIL)


def test_hs3_responder_selects_braille():
    hs = HybridHandshake()
    resp = hs.full_handshake_responder(['HELLO', 'VERSION 1.0', 'ENCODING morse,braille'])
    check("responder_selects_braille", PASS if 'ENCODING_ACK braille' in resp else FAIL)


def test_hs4_incompatible_encoding_raises():
    try:
        HybridHandshake().full_handshake_initiator('base64')
        check("incompatible_rejected", FAIL)
    except HandshakeError:
        check("incompatible_rejected", PASS)


def test_hs5_reset_reverts_to_morse():
    hs = HybridHandshake()
    hs.full_handshake_initiator('morse,braille')
    assert hs.encoder.encoding == ENCODING_BRAILLE
    hs.reset()
    check("reset_reverts", PASS if hs.encoder.encoding == ENCODING_MORSE else FAIL)
    check("reset_clears_peer", PASS if hs.peer_encodings is None else FAIL)
    check("reset_state_closed", PASS if hs.state.name == 'CLOSED' else FAIL)


def test_hs6_responder_to_morse_only():
    hs = HybridHandshake()
    resp = hs.full_handshake_responder(['HELLO', 'ENCODING morse'])
    check("responder_morse_only",
          PASS if 'ENCODING_ACK morse' in resp else FAIL)


# ── Hybrid DSP tests ─────────────────────────────────────────────────

def test_dsp1_braille_roundtrip():
    ds = DiffState(encoding=ENCODING_BRAILLE)
    frame = ds.diff(b'AB')
    ds2 = DiffState(encoding=ENCODING_BRAILLE)
    ds2.apply(frame)
    check("braille_dsp_roundtrip", PASS if ds2.state == b'AB' else FAIL,
          f"got {ds2.state}")


def test_dsp2_braille_multi_byte():
    ds = DiffState(encoding=ENCODING_BRAILLE)
    ds.diff(b'\x00\x00\x00')
    ds.diff(b'\x41\x00\xFF')
    check("braille_multi_byte", PASS if ds.state == b'\x41\x00\xFF' else FAIL,
          f"state={ds.state.hex()}")


def test_dsp3_morse_braille_compatibility():
    """Morse-encoded frame must be decodable by Morse decoder (not cross-encoding)."""
    ds_m = DiffState(encoding=ENCODING_MORSE)
    ds_b = DiffState(encoding=ENCODING_BRAILLE)
    m_frame = ds_m.diff(b'AB')
    try:
        ds_b.apply(m_frame)
        check("cross_encoding_rejected", FAIL)
    except Exception:
        check("cross_encoding_rejected", PASS)


def test_dsp4_braille_sync():
    ds = DiffState(encoding=ENCODING_BRAILLE)
    frame = ds.sync(b'HELLO')
    ds2 = DiffState(encoding=ENCODING_BRAILLE)
    ds2.apply(frame)
    check("braille_sync", PASS if ds2.state == b'HELLO' else FAIL)


# ── Failsafe + hybrid ─────────────────────────────────────────────────

def test_fs1_braille_roundtrip():
    fs = FailsafePM1(encoding=ENCODING_BRAILLE)
    data = b'\x41\x42\x43\x44\x45\x46\x47\x48'
    encoded = fs.encode(data)
    check("braille_failsafe_encode", PASS if encoded else FAIL)
    if encoded:
        decoded = fs.decode(encoded)
        check("braille_failsafe_roundtrip", PASS if decoded == data else FAIL,
              f"got {decoded.hex() if decoded else 'None'}")


def test_fs2_braille_hamming_ecc():
    """Hamming ECC works regardless of encoding layer."""
    fs = FailsafePM1(encoding=ENCODING_BRAILLE)
    data = b'\x41\x42\x43\x44\x45\x46\x47\x48'
    encoded = fs.encode(data)
    check("braille_hamming_clean", PASS if encoded else FAIL)
    if encoded is None:
        return
    # Flip a character in the Braille string
    import sys
    chars = list(encoded)
    original_char = chars[2]
    # Braille cells are single Unicode chars; flip to a different cell
    alt_char = chr(ord(original_char) ^ 1)
    chars[2] = alt_char
    corrupted = ''.join(chars)
    decoded = fs.decode(corrupted)
    check("braille_hamming_corrected", PASS if decoded == data else FAIL,
          f"expected {data.hex()}, got {decoded.hex() if decoded else 'None'}")


def test_fs3_morse_still_works():
    """Default (Morse) path unaffected."""
    fs = FailsafePM1(encoding=ENCODING_MORSE)
    data = b'\x41' * 8
    encoded = fs.encode(data)
    decoded = fs.decode(encoded)
    check("morse_still_works", PASS if decoded == data else FAIL)


# ── Run ───────────────────────────────────────────────────────────────

def main():
    print("=" * 58)
    print("  PM-1 Handshake + Hybrid DSP Integration Tests")
    print("=" * 58)

    tests = [
        ("HS: Initiator upgrades to Braille", test_hs1_initiator_upgrades_to_braille),
        ("HS: Morse-only peer", test_hs2_morse_only_peer),
        ("HS: Responder selects Braille", test_hs3_responder_selects_braille),
        ("HS: Incompatible rejected", test_hs4_incompatible_encoding_raises),
        ("HS: Reset reverts to Morse", test_hs5_reset_reverts_to_morse),
        ("HS: Responder Morse-only", test_hs6_responder_to_morse_only),
        ("DSP: Braille roundtrip", test_dsp1_braille_roundtrip),
        ("DSP: Braille multi-byte", test_dsp2_braille_multi_byte),
        ("DSP: Cross-encoding rejected", test_dsp3_morse_braille_compatibility),
        ("DSP: Braille sync", test_dsp4_braille_sync),
        ("FS: Braille roundtrip", test_fs1_braille_roundtrip),
        ("FS: Braille Hamming ECC", test_fs2_braille_hamming_ecc),
        ("FS: Morse still works", test_fs3_morse_still_works),
    ]

    for name, fn in tests:
        print(f"\n>>> {name}")
        try:
            fn()
        except Exception as e:
            print(f"  [{FAIL}] {name} crashed: {e}")
            results.append({"test": name, "status": FAIL, "detail": str(e)})

    print("\n" + "=" * 58)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    print(f"  {passed} passed, {failed} failed")
    verdict = PASS if failed == 0 else FAIL
    print(f"  OVERALL: [{verdict}]")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
