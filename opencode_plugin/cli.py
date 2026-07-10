"""PM-1 CLI — one-shot trace recording and session management."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))

from opencode_plugin.adapter import trace_to_state, state_to_trace, TRACES_DIR
from opencode_plugin.failsafe import FailsafePM1


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

    state = trace_to_state(trace)
    fs = FailsafePM1(session_id=slug)
    encoded = fs.encode(state)

    if encoded:
        path = TRACES_DIR / f"{slug}.pm1"
        payload = {
            "pm1_version": 1,
            "session_id": slug,
            "timestamp": trace["timestamp"],
            "n_states": 1,
            "state_width": 8,
            "failsafe": fs.stats(),
            "pm1": encoded,
        }
        if args.action:
            payload["action"] = args.action
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"PM-1: {path}")
    else:
        path = TRACES_DIR / f"{slug}.json"
        trace["_failsafe_fallback"] = True
        path.write_text(json.dumps(trace, indent=2, ensure_ascii=False))
        print(f"JSON (fallback): {path}")

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
        print(f"States:    {payload.get('n_states', 0)}")
        print(f"Failsafe:  {payload.get('failsafe', {})}")
        if payload.get("action"):
            print(f"Action:    {payload['action']}")
        morse_len = len(payload["pm1"])
        print(f"Morse:     {morse_len} chars ({morse_len * 0.0039:.1f} tokens at ~3.9 tok/char)")
    else:
        print(f"Format: fallback JSON")
        print(f"Agent:  {payload.get('agent', '?')}")
        print(f"Outcome:{payload.get('outcome', '?')}")


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

    ip = sub.add_parser("info", help="Inspect a trace file")
    ip.add_argument("path", help="Path to .pm1 or .json trace")

    args = parser.parse_args()
    if args.command == "trace":
        return trace_one(args)
    elif args.command == "info":
        return info_cmd(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
