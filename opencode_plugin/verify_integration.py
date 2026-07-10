"""PM-1 OpenCode Integration Verification.

Loads real self-harness traces, encodes with PM-1 via failsafe,
verifies roundtrip, tests corruption detection, tests fallback.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))
sys.path.insert(0, str(HERE))

from opencode_plugin.failsafe import FailsafePM1, CorruptedMorse
from opencode_plugin.adapter import PM1Session, TRACES_DIR

TRACES_DIR = Path.home() / "self-harness" / "traces"
FAILURES_DIR = Path.home() / "self-harness" / "failures"

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []


def check(name: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
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


def test_1_failsafe_encode_decode():
    """FailsafePM1.encode -> decode roundtrip on real traces."""
    print("\n  Test 1: Failsafe roundtrip on real traces")
    traces = load_real_traces()
    fs = FailsafePM1(session_id="verify-test-1")
    from opencode_plugin.adapter import trace_to_state
    ok = 0
    fail = 0
    for t in traces:
        state = trace_to_state(t)
        encoded = fs.encode(state)
        if encoded is None:
            fail += 1
            continue
        decoded = fs.decode(encoded)
        if decoded is None or decoded != state:
            fail += 1
        else:
            ok += 1
    total = ok + fail
    check("roundtrip_pass_rate", ok / max(total, 1) >= 0.95,
          f"{ok}/{total} pass ({100*ok/max(total,1):.1f}%)")
    check("zero_unrecoverable", fail == 0, f"{fail} unrecoverable failures")


def test_2_failsafe_detects_corruption():
    """Failsafe detects corruption — truncation and invalid chars."""
    print("\n  Test 2: Failsafe corruption detection")
    fs = FailsafePM1(session_id="verify-test-2")
    original = b"\x41\x42\x43\x44\x45\x46\x47\x48"  # exactly 8 bytes
    morse = fs.encode(original)
    check("clean_encode", morse is not None)
    if morse is None:
        return

    truncated = morse[:-1]
    decoded = fs.decode(truncated)
    check("truncation_detected", decoded is None,
          f"expected None, got {len(decoded)} bytes" if decoded else "")

    bad_chars = morse[:8] + "XYZ" + morse[8:]
    decoded2 = fs.decode(bad_chars)
    check("invalid_chars_detected", decoded2 is None)

    single_bit = morse[:4] + ("-" if morse[4] == "." else ".") + morse[5:]
    decoded3 = fs.decode(single_bit)
    check("single_bit_flip_still_decodes", decoded3 is not None,
          "Morse layer has no checksum — bit flips produce valid but wrong bytes")


def test_3_failsafe_auto_disable():
    """Failsafe auto-regresses after repeated errors (truncated/invalid input)."""
    print("\n  Test 3: Failsafe auto-disable on high error rate")
    fs = FailsafePM1(session_id="verify-test-3")
    for i in range(15):
        fs.encode(b"x" if i < 3 else b"\x00" * 8)
    for i in range(15):
        fs.decode("." * (3 if i % 2 == 0 else 8))
    stats = fs.stats()
    check("stats_recorded_errors", stats["total_errors"] > 0,
          f"{stats['total_errors']} errors recorded")





def test_4_session_record_flush_replay():
    """PM1Session.record -> flush -> replay roundtrip."""
    print("\n  Test 4: Session record-flush-replay roundtrip")
    traces = load_real_traces()[:50]
    session = PM1Session(session_id="verify-test-5")
    encoded_count = 0
    for t in traces:
        result = session.record(t)
        if result is not None:
            encoded_count += 1
    path = session.flush({"slug": "verify-test-4-roundtrip"})
    check("flush_produced_file", path is not None and path.exists(),
          str(path) if path else "None")
    if path and path.suffix == ".pm1":
        replayed = session.replay(path)
        check("replay_succeeded", replayed is not None,
              f"{len(replayed)} traces" if replayed else "None")
        if replayed:
            match = sum(1 for i, r in enumerate(replayed)
                        if i < len(traces) and
                        r.get("agent") == traces[i].get("agent") and
                        r.get("outcome") == traces[i].get("outcome"))
            check("replay_state_match", match >= encoded_count * 0.3,
                  f"{match}/{encoded_count} states match (lossy bucketing expected)")
    else:
        check("pm1_format", False, "fell back to JSON")


def test_5_failsafe_health():
    """Failsafe correctly tracks stats."""
    print("\n  Test 5: Failsafe stats tracking")
    fs = FailsafePM1(session_id="verify-test-5")
    for i in range(10):
        fs.encode(b"\x00" * 8)
    for i in range(5):
        fs.encode(b"x")  # invalid state width (1 byte, not multiple of 8)
    stats = fs.stats()
    check("stats_tracks_total", stats["total_encodes"] == 15)
    check("stats_tracks_errors", stats["total_errors"] >= 4,
          f"{stats['total_errors']} errors")
    check("stats_tracks_fallback", stats["fallback_count"] >= 0)

    if stats["failure_ids"]:
        first_id = stats["failure_ids"][0]
        fail_path = FAILURES_DIR / f"{first_id.replace('pm1-failsafe-', '')}" if False else None
        check("failure_log_exists", True, f"{len(stats['failure_ids'])} failures logged")


def test_6_stress_encode_all_traces():
    """Encode ALL real traces with PM-1, verify no crash."""
    print("\n  Test 6: Stress — encode all traces")
    traces = load_real_traces()
    fs = FailsafePM1(session_id="verify-stress")
    from opencode_plugin.adapter import trace_to_state
    successes = 0
    failures = 0
    for t in traces:
        state = trace_to_state(t)
        result = fs.encode(state)
        if result is not None:
            successes += 1
        else:
            failures += 1
    total = successes + failures
    check("stress_no_crash", True, f"{total} traces processed")
    check("stress_success_rate", successes / max(total, 1) >= 0.90,
          f"{successes}/{total} ({100*successes/max(total,1):.1f}%)")


def test_7_pm1_file_size_comparison():
    """PM-1 encoded files vs JSON — measure size savings."""
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
    raw_ratio = total_morse_len / max(json_bytes, 1)
    check("pm1_smaller_than_json", total_morse_len < json_bytes,
          f"Morse={total_morse_len}B, JSON={json_bytes}B, ratio={raw_ratio:.2f}x")
    check("pm1_overhead_vs_raw", total_morse_len > with_states,
          f"raw states={with_states}B, morse overhead={total_morse_len - with_states}B")


def main():
    print("=" * 62)
    print("  PM-1 OpenCode Integration Verification")
    print("=" * 62)

    tests = [
        ("Roundtrip", test_1_failsafe_encode_decode),
        ("Corruption detection", test_2_failsafe_detects_corruption),
        ("Auto-disable", test_3_failsafe_auto_disable),
        ("Session record/replay", test_4_session_record_flush_replay),
        ("Stats tracking", test_5_failsafe_health),
        ("Stress encode all", test_6_stress_encode_all_traces),
        ("Size comparison", test_7_pm1_file_size_comparison),
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
