"""PM-1 CLI — one-shot trace recording, inspection, and savings audit."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))

from opencode_plugin.adapter import trace_to_state, state_to_trace, TRACES_DIR
from opencode_plugin.failsafe import FailsafePM1
from hybrid import ENCODING_MORSE, ENCODING_BRAILLE


TOK_PER_CHAR = {"morse": 0.125, "braille": 1.0}


def _estimate_json_bytes(trace: dict) -> int:
    """Estimate how many bytes a compact JSON version of this trace would be."""
    return len(json.dumps(trace, separators=(",", ":"), ensure_ascii=False).encode())


def _format_savings(pm1_size: int, json_size: int) -> str:
    ratio = pm1_size / max(json_size, 1)
    pct = (1 - ratio) * 100
    if pct >= 0:
        return f"ratio={ratio:.2f}x, saved {pct:.1f}%"
    else:
        return f"ratio={ratio:.2f}x, { -pct:.1f}% overhead"


def trace_one(args):
    trace = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": args.agent,
        "outcome": args.outcome,
        "duration_s": args.duration_s,
        "tool_calls": args.tool_calls,
        "key_files": args.key_files or [],
        "action": args.action or "",
        "failure": {"category": args.fail_category, "severity": args.fail_severity} if args.fail_category else {},
        "validation": not args.no_validation,
    }
    if args.slug:
        trace["slug"] = args.slug

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    slug = args.slug or f"{now}-{args.agent}-cli"
    json_ref_size = _estimate_json_bytes(trace)

    state = trace_to_state(trace)
    encoding = args.encoding or ENCODING_MORSE
    fs = FailsafePM1(session_id=slug, encoding=encoding)
    encoded = fs.encode(state)

    if encoded:
        path = TRACES_DIR / f"{slug}.pm1"
        payload = {
            "pm1_version": 1,
            "session_id": slug,
            "timestamp": trace["timestamp"],
            "agent": trace.get("agent", "unknown"),
            "outcome": trace.get("outcome", "unknown"),
            "duration_s": trace.get("duration_s", 0),
            "tool_calls": trace.get("tool_calls", 0),
            "key_files": trace.get("key_files", []),
            "failure": trace.get("failure", {}),
            "encoding": encoding,
            "n_states": 1,
            "state_width": 8,
            "failsafe": fs.stats(),
            "pm1": encoded,
        }
        if args.action:
            payload["action"] = args.action
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        savings = _format_savings(len(encoded), json_ref_size)
        tok_per_char = TOK_PER_CHAR.get(encoding, 0.125)
        print(f"PM-1: {path}")
        print(f"       {len(encoded)} chars ({len(encoded) * tok_per_char:.1f} tok, {encoding}) — {savings}")
    else:
        path = TRACES_DIR / f"{slug}.json"
        trace["_failsafe_fallback"] = True
        path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON (fallback): {path} — {json_ref_size} B")

    return 0


def info_cmd(args):
    path = Path(args.path)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Not a valid PM-1 file: {e}", file=sys.stderr)
        return 1

    if payload.get("pm1_version") == 1 and "pm1" in payload:
        print(f"Version:   PM-1 v{payload['pm1_version']}")
        print(f"Session:   {payload.get('session_id', '?')}")
        print(f"Timestamp: {payload.get('timestamp', '?')}")
        print(f"Encoding:  {payload.get('encoding', 'morse')}")
        print(f"States:    {payload.get('n_states', 0)}")
        print(f"Failsafe:  {payload.get('failsafe', {})}")
        if payload.get("action"):
            print(f"Action:    {payload['action']}")
        enc = payload.get("encoding", "morse")
        payload_len = len(payload["pm1"])
        tok_per_char = TOK_PER_CHAR.get(enc, 0.125)
        tok_est = payload_len * tok_per_char
        sv = payload.get("savings")
        if sv:
            print(f"Payload:   {payload_len} chars ({tok_est:.0f} tok, {enc}) — "
                  f"ratio={sv['ratio']}x, saved {sv['savings_pct']}%")
        else:
            json_size = _estimate_json_bytes(payload)
            s = _format_savings(payload_len, json_size)
            print(f"Payload:   {payload_len} chars ({tok_est:.0f} tok, {enc}) — {s}")
    else:
        print(f"Format: fallback JSON")
        print(f"Agent:  {payload.get('agent', '?')}")
        print(f"Outcome:{payload.get('outcome', '?')}")


def audit_cmd(args):
    pm1_dir = Path(args.dir or TRACES_DIR)
    if not pm1_dir.is_dir():
        print(f"Directory not found: {pm1_dir}", file=sys.stderr)
        return 1

    pm1_files = sorted(pm1_dir.glob("*.pm1"))
    json_files = sorted(pm1_dir.glob("*.json"))

    if not pm1_files and not json_files:
        print(f"No trace files found in {pm1_dir}")
        return 0

    total_pm1_chars = 0
    total_json_bytes = 0
    pm1_count = 0
    json_count = 0
    by_encoding = {"morse": {"count": 0, "chars": 0, "json_bytes": 0},
                   "braille": {"count": 0, "chars": 0, "json_bytes": 0}}

    for f in pm1_files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("pm1_version") == 1 and "pm1" in payload:
            pm1_chars = len(payload["pm1"])
            sv = payload.get("savings")
            json_bytes = sv["json_bytes"] if sv else _estimate_json_bytes(payload)
            total_pm1_chars += pm1_chars
            total_json_bytes += json_bytes
            pm1_count += 1
            enc = payload.get("encoding", "morse")
            if enc in by_encoding:
                by_encoding[enc]["count"] += 1
                by_encoding[enc]["chars"] += pm1_chars
                by_encoding[enc]["json_bytes"] += json_bytes

    json_count = len(json_files)

    print(f"PM-1 trace audit: {pm1_dir}")
    print(f"  {'=' * 50}")
    print(f"  Total .pm1 files:  {pm1_count}")
    print(f"  Total .json files: {json_count}")
    if pm1_count > 0:
        ratio = total_pm1_chars / max(total_json_bytes, 1)
        pct = (1 - ratio) * 100
        print(f"  {'=' * 50}")
        print(f"  PM-1 chars:     {total_pm1_chars:>8,}")
        print(f"  JSON equivalent:{total_json_bytes:>8,} B")
        print(f"  Ratio:          {ratio:.2f}x")
        print(f"  Savings:        {pct:.1f}%")
        print(f"  {'=' * 50}")
        for enc, data in sorted(by_encoding.items()):
            if data["count"] > 0:
                r = data["chars"] / max(data["json_bytes"], 1)
                p = (1 - r) * 100
                print(f"  [{enc}] {data['count']} files: {data['chars']} chars vs {data['json_bytes']} B ({p:.1f}%)")

    print(f"\n  Trace dir: {pm1_dir.resolve()}")

    # Generate HTML dashboard if --html was given
    if getattr(args, "html", None):
        from opencode_plugin.dashboard import generate_html_report
        html_path = generate_html_report(args.html)
        print(f"  HTML report: {html_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="PM-1 trace recorder")
    sub = parser.add_subparsers(dest="command")

    tp = sub.add_parser("trace", help="Record a single trace")
    tp.add_argument("--agent", required=True, help="Agent name (orchestrator, general, fixer, ...)")
    tp.add_argument("--outcome", default="pass", choices=["pass", "fail", "partial", "unknown"])
    tp.add_argument("--duration-s", type=int, default=0, help="Duration in seconds")
    tp.add_argument("--tool-calls", type=int, default=0)
    tp.add_argument("--key-files", nargs="*", default=[], help="Key files touched")
    tp.add_argument("--action", default="", help="Free-text action summary (stored verbatim in trace)")
    tp.add_argument("--slug", default="", help="Custom slug (default: timestamp-agent-cli)")
    tp.add_argument("--fail-category", default="", help="Failure category (tool, config, workflow, ...)")
    tp.add_argument("--fail-severity", default="", help="Failure severity (low, medium, high)")
    tp.add_argument("--no-validation", action="store_true", help="Skip validation flag")
    tp.add_argument("--encoding", default="", choices=["", "morse", "braille"],
                    help="Encoding: morse (default) or braille")

    ip = sub.add_parser("info", help="Inspect a trace file")
    ip.add_argument("path", help="Path to .pm1 or .json trace")

    ap = sub.add_parser("audit", help="Scan all traces and show aggregate savings")
    ap.add_argument("--dir", default="", help="Trace directory (default: ~/self-harness/traces)")
    ap.add_argument("--html", type=str, default="", help="Generate HTML dashboard report at PATH")

    args = parser.parse_args()
    if args.command == "trace":
        return trace_one(args)
    elif args.command == "info":
        return info_cmd(args)
    elif args.command == "audit":
        return audit_cmd(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
