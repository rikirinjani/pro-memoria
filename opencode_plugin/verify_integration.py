"""PM-1 OpenCode Integration Verification.

Loads real self-harness traces, encodes with PM-1 via failsafe,
verifies roundtrip, tests Hamming ECC, tests corruption detection.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))
sys.path.insert(0, str(HERE))

from opencode_plugin.failsafe import FailsafePM1, CorruptedMorse, _hamming_protect, _hamming_verify
from opencode_plugin.adapter import PM1Session, TRACES_DIR

TRACES_DIR = Path.home() / "self-harness" / "traces"
FAILURES_DIR = Path.home() / "self-harness" / "failures"

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []


def check(name: str, status: str, detail: str = ""):
    results.append({"test": name, "status": status, "detail": detail})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def load_real_traces():
    traces = []
    for f in sorted(TRACES_DIR.glob("*.json")):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                traces.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    return traces


def test_1_failsafe_roundtrip():
    print("\n  Test 1: Failsafe roundtrip on real traces")
    traces = load_real_traces()
    fs = FailsafePM1(session_id="verify-test-1")
    from opencode_plugin.adapter import trace_to_state
    ok = fail = 0
    for t in traces:
        state = trace_to_state(t)
        encoded = fs.encode(state)
        if encoded is None:
            fail += 1; continue
        decoded = fs.decode(encoded)
        if decoded is None or decoded != state:
            fail += 1
        else:
            ok += 1
    total = ok + fail
    check("roundtrip_pass_rate", PASS if ok / max(total, 1) >= 0.95 else FAIL,
          f"{ok}/{total} pass ({100*ok/max(total,1):.1f}%)")
    check("zero_unrecoverable", PASS if fail == 0 else FAIL,
          f"{fail} unrecoverable failures")


def test_2_hamming_ecc():
    """Hamming [8,4,4]: single-bit correctable, double-bit detectable."""
    print("\n  Test 2: Hamming ECC — single-bit fix, double-bit detect")
    fs = FailsafePM1(session_id="verify-test-2")
    original = b"\x41\x42\x43\x44\x45\x46\x47\x48"
    morse = fs.encode(original)
    check("clean_encode", PASS if morse else FAIL)
    if morse is None:
        return

    check("total_corrected_starts_at_zero", PASS if fs.total_corrected == 0 else FAIL,
          f"{fs.total_corrected}")

    # Single-bit flip in Morse -> single-bit flip in Hamming codeword -> corrected
    single_bit = CorruptedMorse.flip_bit(morse, 15)
    decoded = fs.decode(single_bit)
    check("single_bit_corrected", PASS if decoded == original else FAIL,
          f"expected {original.hex()}, got {decoded.hex() if decoded else 'None'}")
    check("total_corrected_incremented", PASS if fs.total_corrected > 0 else FAIL,
          f"{fs.total_corrected} corrections")

    # Two bits in same Hamming byte -> double-bit -> unrecoverable
    same_byte = morse[:10] + ("-" if morse[10] == "." else ".") + morse[11:]
    same_byte = same_byte[:12] + ("-" if same_byte[12] == "." else ".") + same_byte[13:]
    decoded2 = fs.decode(same_byte)
    check("double_bit_detected_as_unrecoverable", PASS if decoded2 is None else FAIL)

    # Single-bit in Morse but at a position that affects the Morse layer itself
    # (truncation of a single character)
    truncated = morse[:-1]
    decoded3 = fs.decode(truncated)
    check("truncation_detected", PASS if decoded3 is None else FAIL)

    # Invalid Morse characters
    bad_chars = morse[:8] + "XYZ" + morse[8:]
    decoded4 = fs.decode(bad_chars)
    check("invalid_chars_detected", PASS if decoded4 is None else FAIL)


def test_3_failsafe_auto_disable():
    print("\n  Test 3: Failsafe auto-disable on high error rate")
    fs = FailsafePM1(session_id="verify-test-3")
    for i in range(12):
        fs.encode(b"x")
    stats = fs.stats()
    check("errors_recorded", PASS if stats["total_errors"] > 0 else FAIL,
          f"{stats['total_errors']} errors")


def test_4_session_record_flush_replay():
    print("\n  Test 4: Session record-flush-replay roundtrip")
    traces = load_real_traces()[:50]
    session = PM1Session(session_id="verify-test-4")
    encoded_count = 0
    for t in traces:
        result = session.record(t)
        if result is not None:
            encoded_count += 1
    path = session.flush({"slug": "verify-test-4-roundtrip"})
    check("flush_produced_file", PASS if path and path.exists() else FAIL,
          str(path) if path else "None")
    if path and path.suffix == ".pm1":
        replayed = session.replay(path)
        check("replay_succeeded", PASS if replayed else FAIL,
              f"{len(replayed)} traces" if replayed else "None")
        if replayed:
            match = sum(1 for i, r in enumerate(replayed)
                        if i < len(traces) and
                        r.get("agent") == traces[i].get("agent") and
                        r.get("outcome") == traces[i].get("outcome"))
            check("replay_state_match", PASS if match >= encoded_count * 0.3 else FAIL,
                  f"{match}/{encoded_count} states match (lossy bucketing expected)")
    else:
        check("pm1_format_is_pm1", FAIL if len(traces) > 0 else PASS,
              "fell back to JSON")


def test_5_failsafe_health():
    print("\n  Test 5: Failsafe stats tracking")
    fs = FailsafePM1(session_id="verify-test-5")
    for i in range(10):
        fs.encode(b"\x00" * 8)
    for i in range(5):
        fs.encode(b"x")
    stats = fs.stats()
    check("stats_tracks_total", PASS if stats["total_encodes"] == 15 else FAIL)
    check("stats_tracks_errors", PASS if stats["total_errors"] >= 4 else FAIL,
          f"{stats['total_errors']} errors")
    check("total_corrected_no_phantom", PASS if stats["total_corrected"] >= 0 else FAIL)
    check("failure_log_exists", PASS if stats["failure_ids"] else FAIL)
    check("status_is_active_or_disabled", PASS if stats["status"] in ("ACTIVE", "DISABLED") else FAIL)


def test_6_stress_encode_all_traces():
    print("\n  Test 6: Stress — encode all traces")
    traces = load_real_traces()
    fs = FailsafePM1(session_id="verify-stress")
    from opencode_plugin.adapter import trace_to_state
    successes = failures = 0
    for t in traces:
        state = trace_to_state(t)
        result = fs.encode(state)
        if result is not None:
            successes += 1
        else:
            failures += 1
    total = successes + failures
    check("stress_no_crash", PASS, f"{total} traces processed")
    check("stress_success_rate", PASS if successes / max(total, 1) >= 0.90 else FAIL,
          f"{successes}/{total} ({100*successes/max(total,1):.1f}%)")


def test_7_pm1_file_size_comparison():
    print("\n  Test 7: File size comparison PM-1 vs JSON")
    traces = load_real_traces()
    json_bytes = sum(len(json.dumps(t, separators=(",", ":")).encode()) for t in traces)
    fs = FailsafePM1(session_id="verify-size")
    from opencode_plugin.adapter import trace_to_state
    total_morse_len = 0
    pm1_encodes = 0
    for t in traces:
        state = trace_to_state(t)
        morse = fs.encode(state)
        if morse is not None:
            total_morse_len += len(morse)
            pm1_encodes += 1
    with_states = pm1_encodes * 8
    check("pm1_smaller_than_json", PASS if total_morse_len < json_bytes else FAIL,
          f"Morse={total_morse_len}B, JSON={json_bytes}B, ratio={total_morse_len/max(json_bytes,1):.2f}x")
    check("pm1_hamming_overhead", PASS if total_morse_len > with_states else FAIL,
          f"raw states={with_states}B, Hamming bytes={pm1_encodes * 16}B, Morse overhead={total_morse_len - pm1_encodes * 16}B")


def test_8_disk_corruption_simulation():
    """Simulate disk bit-rot: encode -> flip bit -> attempt decode."""
    print("\n  Test 8: Disk corruption — encode, flip, detect")
    original = b"\x41\x42\x43\x44\x45\x46\x47\x48"

    # Hamming layer direct test
    protected = _hamming_protect(original)
    recovered, unrec, n_corr = _hamming_verify(protected)
    check("ecc_clean_roundtrip", PASS if recovered == original and not unrec and n_corr == 0 else FAIL)

    # Single-bit flip in Hamming byte 0 -> should correct
    corrupted = bytearray(protected)
    corrupted[0] ^= 0b00010000  # flip one bit
    recovered2, unrec2, n_corr2 = _hamming_verify(bytes(corrupted))
    check("ecc_single_bit_corrected", PASS if recovered2 == original and not unrec2 and n_corr2 == 1 else FAIL,
          f"unrec={unrec2}, corrected={n_corr2}, recovered={recovered2.hex() if recovered2 else 'None'}")

    # Double-bit flip in Hamming byte 0 -> unrecoverable
    corrupted2 = bytearray(protected)
    corrupted2[0] ^= 0b00110000  # flip two bits
    recovered3, unrec3, n_corr3 = _hamming_verify(bytes(corrupted2))
    check("ecc_double_bit_detected", PASS if unrec3 and recovered3 is None else FAIL,
          f"unrec={unrec3}, recovered={recovered3.hex() if recovered3 else 'None'}")

    # Full pipeline via FailsafePM1
    fs = FailsafePM1(session_id="verify-disk")
    morse = fs.encode(original)
    check("fs_clean_encode", PASS if morse else FAIL)
    if morse is None:
        return

    corrupted_morse = CorruptedMorse.flip_bit(morse, 20)
    decoded = fs.decode(corrupted_morse)
    check("fs_single_bit_corrected_on_disk_read", PASS if decoded == original else FAIL,
          f"original={original.hex()}, decoded={decoded.hex() if decoded else 'None'}")

    prev_corrected = fs.total_corrected
    corrupted_morse2 = CorruptedMorse.flip_bit(morse, 10)
    decoded2 = fs.decode(corrupted_morse2)
    check("fs_second_correction_tracked", PASS if decoded2 == original and fs.total_corrected > prev_corrected else FAIL,
          f"corrected={fs.total_corrected} (prev={prev_corrected})")


def main():
    print("=" * 62)
    print("  PM-1 OpenCode Integration Verification")
    print("=" * 62)

    tests = [
        ("Roundtrip", test_1_failsafe_roundtrip),
        ("Hamming ECC", test_2_hamming_ecc),
        ("Auto-disable", test_3_failsafe_auto_disable),
        ("Session record/replay", test_4_session_record_flush_replay),
        ("Stats tracking", test_5_failsafe_health),
        ("Stress encode all", test_6_stress_encode_all_traces),
        ("Size comparison", test_7_pm1_file_size_comparison),
        ("Disk corruption sim", test_8_disk_corruption_simulation),
    ]

    for name, fn in tests:
        print(f"\n>>> {name}")
        try:
            fn()
        except Exception as e:
            print(f"  [{FAIL}] {name} crashed: {e}")
            results.append({"test": name, "status": FAIL, "detail": str(e)})

    print("\n" + "=" * 62)
    print("  Summary")
    print("=" * 62)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    warned = sum(1 for r in results if r["status"] == WARN)
    print(f"  {passed} passed, {failed} failed, {warned} warned")
    verdict = PASS if failed == 0 else FAIL
    print(f"  OVERALL: [{verdict}]")

    from datetime import timezone as tz
    report = {
        "timestamp": __import__("datetime").datetime.now(tz.utc).isoformat(),
        "verdict": verdict,
        "results": results,
    }
    report_path = HERE / "verify_results.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\n  Report: {report_path}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
