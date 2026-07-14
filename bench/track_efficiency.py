"""Pro Memoria — Ongoing Efficiency Tracker.

Records aggregate PM-1 savings snapshots to a CSV history file for trend
tracking. Run anytime to capture current efficiency and see how it evolves.

Usage:
    python -m bench.track_efficiency
    python -m bench.track_efficiency --history-only  # just show trend, don't snapshot
"""

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
TRACES_DIR = Path.home() / "self-harness" / "traces"
HISTORY_FILE = RESULTS / "efficiency_history.csv"

# Must be importable from parent
sys.path.insert(0, str(HERE.parent))
from hybrid import ENCODING_MORSE, ENCODING_BRAILLE
TOK_PER_CHAR = {"morse": 0.125, "braille": 1.0}


def _estimate_json_bytes(payload: dict) -> int:
    return len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())


def snapshot() -> dict:
    """Run an audit snapshot: count .pm1 files, chars, and JSON equivalent."""
    if not TRACES_DIR.is_dir():
        return {"error": f"Traces dir not found: {TRACES_DIR}"}

    pm1_files = sorted(TRACES_DIR.glob("*.pm1"))
    json_files = sorted(TRACES_DIR.glob("*.json"))

    total_pm1_chars = 0
    total_json_bytes = 0
    pm1_count = 0
    by_encoding = {
        "morse": {"count": 0, "chars": 0, "json_bytes": 0},
        "braille": {"count": 0, "chars": 0, "json_bytes": 0},
    }

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
    ratio = total_pm1_chars / max(total_json_bytes, 1)
    savings_pct = round((1 - ratio) * 100, 1)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pm1_files": pm1_count,
        "json_files": json_count,
        "total_pm1_chars": total_pm1_chars,
        "total_json_bytes": total_json_bytes,
        "ratio": round(ratio, 3),
        "savings_pct": savings_pct,
        "by_encoding": by_encoding,
    }
    return result


def append_history(snap: dict) -> None:
    """Append a snapshot row to the CSV history file."""
    RESULTS.mkdir(exist_ok=True)
    is_new = not HISTORY_FILE.exists()
    with open(HISTORY_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "pm1_files", "json_files",
                         "pm1_chars", "json_bytes", "ratio", "savings_pct"])
        w.writerow([
            snap["timestamp"],
            snap["pm1_files"],
            snap["json_files"],
            snap["total_pm1_chars"],
            snap["total_json_bytes"],
            snap["ratio"],
            snap["savings_pct"],
        ])


def load_history() -> list[dict]:
    """Load historical snapshots from CSV."""
    if not HISTORY_FILE.exists():
        return []
    rows = []
    with open(HISTORY_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["pm1_files"] = int(row["pm1_files"])
            row["json_files"] = int(row["json_files"])
            row["pm1_chars"] = int(row["pm1_chars"])
            row["json_bytes"] = int(row["json_bytes"])
            row["ratio"] = float(row["ratio"])
            row["savings_pct"] = float(row["savings_pct"])
            rows.append(row)
    return rows


def print_snapshot(snap: dict) -> None:
    """Pretty-print a snapshot."""
    print(f"PM-1 efficiency snapshot: {snap['timestamp']}")
    print(f"  {'=' * 50}")
    print(f"  .pm1 files:     {snap['pm1_files']}")
    print(f"  .json files:    {snap['json_files']}")
    print(f"  {'=' * 50}")
    print(f"  PM-1 chars:     {snap['total_pm1_chars']:>8,}")
    print(f"  JSON equiv:     {snap['total_json_bytes']:>8,} B")
    print(f"  Ratio:          {snap['ratio']:.3f}x")
    print(f"  Savings:        {snap['savings_pct']:.1f}%")
    for enc, data in sorted(snap.get("by_encoding", {}).items()):
        if data["count"] > 0:
            r = data["chars"] / max(data["json_bytes"], 1)
            p = (1 - r) * 100
            print(f"    [{enc}] {data['count']} files: {p:.1f}%")
    print()


def print_trend(history: list[dict]) -> None:
    """Show efficiency trend over time."""
    if not history:
        print("  No history yet.")
        return

    first = history[0]
    last = history[-1]
    savings = [h["savings_pct"] for h in history]

    print(f"Efficiency trend: {len(history)} snapshots recorded")
    print(f"  {'=' * 50}")
    print(f"  First:   {first['timestamp'][:19]} — "
          f"{first['pm1_files']} files, {first['savings_pct']:.1f}% savings")
    print(f"  Latest:  {last['timestamp'][:19]} — "
          f"{last['pm1_files']} files, {last['savings_pct']:.1f}% savings")
    print(f"  Min:     {min(savings):.1f}%")
    print(f"  Max:     {max(savings):.1f}%")
    print(f"  Avg:     {sum(savings)/len(savings):.1f}%")
    if len(savings) >= 2:
        delta = last["savings_pct"] - first["savings_pct"]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        print(f"  Trend:   {arrow} {delta:+.1f}% from first snapshot")
    print(f"  History: {HISTORY_FILE}")
    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PM-1 efficiency tracker")
    parser.add_argument("--history-only", action="store_true",
                        help="Just show trend, don't record a new snapshot")
    args = parser.parse_args()

    history = load_history()

    if not args.history_only:
        snap = snapshot()
        if "error" in snap:
            print(f"Error: {snap['error']}", file=sys.stderr)
            return 1
        append_history(snap)
        print_snapshot(snap)

    if history or args.history_only:
        # Reload to include just-written snapshot
        print_trend(load_history())

    return 0


if __name__ == "__main__":
    sys.exit(main())
