"""PM-1 Dashboard — self-contained HTML savings report with ECharts visualizations.

Usage:
    python -m opencode_plugin.dashboard [--output report.html]

Or via CLI:
    pm1-trace audit --html report.html
"""

import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MORSE = HERE.parent
sys.path.insert(0, str(MORSE))

from opencode_plugin.adapter import TRACES_DIR

# Reuse the same estimator from cli.py
def _estimate_json_bytes(payload: dict) -> int:
    """Estimate how many bytes a compact JSON version of this trace would be."""
    return len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())


def _scan_traces() -> dict:
    """Scan TRACES_DIR and return aggregated stats dict.

    Reads all .pm1 and .json files, computes savings, agent/encoding/daily
    breakdowns, and a per-file detail list.
    """
    traces_dir = TRACES_DIR
    pm1_files = sorted(traces_dir.glob("*.pm1"))
    json_files = sorted(traces_dir.glob("*.json"))

    total_pm1_chars = 0
    total_json_bytes = 0
    pm1_count = 0
    json_count = 0

    per_agent: dict[str, dict] = {}
    per_encoding: dict[str, dict] = {}
    daily: dict[str, dict] = {}
    detail: list[dict] = []
    top_savers: list[dict] = []

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

            agent = payload.get("agent", "unknown")
            _accum(per_agent, agent, pm1_chars, json_bytes)

            encoding = payload.get("encoding", "morse")
            _accum(per_encoding, encoding, pm1_chars, json_bytes)

            ts = payload.get("timestamp", "")
            day_key = _parse_day(ts)
            if day_key:
                _accum(daily, day_key, pm1_chars, json_bytes)

            ratio = pm1_chars / max(json_bytes, 1)
            savings_pct = (1 - ratio) * 100
            savings_bytes = json_bytes - pm1_chars

            detail.append({
                "filename": f.name,
                "timestamp": ts,
                "date": ts[:10] if ts else "",
                "agent": agent,
                "encoding": encoding,
                "pm1_chars": pm1_chars,
                "json_bytes": json_bytes,
                "savings_pct": round(savings_pct, 1),
                "savings_bytes": savings_bytes,
            })
            top_savers.append({
                "filename": f.name,
                "agent": agent,
                "savings_bytes": savings_bytes,
            })

    for f in json_files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        json_count += 1
        total_json_bytes += size
        detail.append({
            "filename": f.name,
            "timestamp": "",
            "date": "",
            "agent": "json-fallback",
            "encoding": "json",
            "pm1_chars": 0,
            "json_bytes": size,
            "savings_pct": 0.0,
            "savings_bytes": 0,
        })

    top_savers.sort(key=lambda x: x["savings_bytes"], reverse=True)

    ratio = total_pm1_chars / max(total_json_bytes, 1)
    savings_pct = (1 - ratio) * 100

    return {
        "pm1_count": pm1_count,
        "json_count": json_count,
        "total_files": pm1_count + json_count,
        "total_pm1_chars": total_pm1_chars,
        "total_json_bytes": total_json_bytes,
        "ratio": round(ratio, 4),
        "savings_pct": round(savings_pct, 1),
        "per_agent": per_agent,
        "per_encoding": per_encoding,
        "daily": dict(sorted(daily.items())),
        "detail": detail,
        "top_savers": top_savers[:10],
    }


def _accum(d: dict, key: str, pm1_chars: int, json_bytes: int) -> None:
    """Accumulate counts/chars/bytes into a nested dict bucket."""
    if key not in d:
        d[key] = {"count": 0, "pm1_chars": 0, "json_bytes": 0}
    d[key]["count"] += 1
    d[key]["pm1_chars"] += pm1_chars
    d[key]["json_bytes"] += json_bytes


def _parse_day(ts: str) -> str | None:
    """Extract YYYY-MM-DD from an ISO timestamp string, or None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _compute_savings_pct(pm1_chars: int, json_bytes: int) -> float:
    """Return savings percentage (positive = saving, negative = overhead)."""
    return round((1 - pm1_chars / max(json_bytes, 1)) * 100, 1)


# ── HTML Template ──────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PM-1 Efficiency Report</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; color: #2d3436; }

/* Header */
.header { background: linear-gradient(135deg, #2c3e50 0%, #1a252f 100%); color: #fff; padding: 32px 40px; }
.header h1 { font-size: 28px; font-weight: 600; letter-spacing: -0.5px; }
.header .subtitle { font-size: 14px; color: #95a5a6; margin-top: 6px; }
.header .subtitle span { color: #bdc3c7; }
.header .meta { margin-top: 12px; font-size: 14px; display: flex; flex-wrap: wrap; gap: 20px; }
.header .meta-item { color: #ecf0f1; }
.header .meta-item strong { color: #f1c40f; }

/* Container */
.container { max-width: 1400px; margin: 0 auto; padding: 24px; }

/* Summary Cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 28px; }
.card { background: #fff; border-radius: 10px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.card .label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; color: #7f8c8d; margin-bottom: 6px; }
.card .value { font-size: 28px; font-weight: 700; }
.card .value.green { color: #27ae60; }
.card .value.blue { color: #2980b9; }
.card .value.orange { color: #e67e22; }
.card .value.purple { color: #8e44ad; }

/* Chart Grid */
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
@media (max-width: 900px) { .chart-row { grid-template-columns: 1fr; } }
.chart-box { background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.chart-box h3 { font-size: 14px; font-weight: 600; color: #2c3e50; margin-bottom: 10px; }
.chart-canvas { width: 100%; height: 320px; }

/* Table */
.table-wrap { background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow-x: auto; margin-bottom: 24px; }
.table-wrap h3 { font-size: 14px; font-weight: 600; color: #2c3e50; margin-bottom: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead { background: #f8f9fa; }
th { text-align: left; padding: 10px 12px; font-weight: 600; color: #2c3e50; border-bottom: 2px solid #eee; white-space: nowrap; cursor: pointer; user-select: none; }
th:hover { color: #2980b9; }
th.sort-asc::after { content: " \25B2"; font-size: 10px; }
th.sort-desc::after { content: " \25BC"; font-size: 10px; }
td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }
tr:hover { background: #fafbfc; }
td.mono { font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-size: 12px; }
tr.json-row { color: #95a5a6; font-style: italic; }

/* Footer */
.footer { text-align: center; padding: 20px; font-size: 12px; color: #95a5a6; }

/* Savings badge */
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge.save { background: #d5f5e3; color: #1e8449; }
.badge.over { background: #fdebd0; color: #b7950b; }
.badge.none { background: #ebedef; color: #717d7e; }
</style>
</head>
<body>

<div class="header">
  <h1>PM-1 Efficiency Report</h1>
  <div class="subtitle">Generated: <span>__GENERATED__</span> &middot; __TRACES_DIR__</div>
  <div class="meta">
    <div class="meta-item">Total traces: <strong>__TOTAL_FILES__</strong></div>
    <div class="meta-item">PM-1: <strong>__PM1_COUNT__</strong></div>
    <div class="meta-item">JSON (fallback): <strong>__JSON_COUNT__</strong></div>
    <div class="meta-item">Active agents: <strong>__AGENT_COUNT__</strong></div>
  </div>
</div>

<div class="container">

  <!-- Summary Cards -->
  <div class="cards">
    <div class="card">
      <div class="label">Total Trace Files</div>
      <div class="value blue">__TOTAL_FILES__</div>
    </div>
    <div class="card">
      <div class="label">PM-1 Characters</div>
      <div class="value orange">__PM1_CHARS__</div>
    </div>
    <div class="card">
      <div class="label">JSON Bytes Saved</div>
      <div class="value green">__JSON_SAVED__</div>
    </div>
    <div class="card">
      <div class="label">Overall Savings</div>
      <div class="value purple">__SAVINGS_PCT__%</div>
    </div>
  </div>

  <!-- Chart Row 1: Savings over time + Per-agent breakdown -->
  <div class="chart-row">
    <div class="chart-box">
      <h3>Savings Over Time (daily)</h3>
      <div id="chart-timeseries" class="chart-canvas"></div>
    </div>
    <div class="chart-box">
      <h3>Per-Agent Savings</h3>
      <div id="chart-agents" class="chart-canvas"></div>
    </div>
  </div>

  <!-- Chart Row 2: Encoding distribution + Top saving traces -->
  <div class="chart-row">
    <div class="chart-box">
      <h3>Encoding Distribution</h3>
      <div id="chart-encoding" class="chart-canvas"></div>
    </div>
    <div class="chart-box">
      <h3>Top Saving Traces</h3>
      <div id="chart-topsavers" class="chart-canvas"></div>
    </div>
  </div>

  <!-- Detail Table -->
  <div class="table-wrap">
    <h3>All Traces</h3>
    <table id="trace-table">
      <thead>
        <tr>
          <th data-col="filename">Filename</th>
          <th data-col="date">Date</th>
          <th data-col="agent">Agent</th>
          <th data-col="encoding">Encoding</th>
          <th data-col="json_bytes" class="mono-col">JSON Bytes</th>
          <th data-col="savings_pct" class="mono-col">Savings %</th>
        </tr>
      </thead>
      <tbody>
__TABLE_ROWS__
      </tbody>
    </table>
  </div>

</div>

<div class="footer">
  PM-1 Efficiency Report &mdash; Pro Memoria Project
</div>

<script>
var savingsPct = __SAVINGS_PCT__;
</script>

<script>
/* ── Chart 1: Savings Over Time ── */
(function() {
  var chart = echarts.init(document.getElementById('chart-timeseries'));
  var dates = __TS_DATES__;
  var values = __TS_VALUES__;
  var option = {
    tooltip: { trigger: 'axis', valueFormatter: function(v) { return v.toFixed(1) + '%'; } },
    grid: { left: '8%', right: '8%', bottom: '12%', top: '10%' },
    xAxis: { type: 'category', data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%' }, min: 0 },
    series: [{
      type: 'line',
      data: values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: '#2980b9', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(41,128,185,0.3)' }, { offset: 1, color: 'rgba(41,128,185,0.02)' }]
      }}
    }]
  };
  chart.setOption(option);
  window.addEventListener('resize', function() { chart.resize(); });
})();

/* ── Chart 2: Per-Agent Savings ── */
(function() {
  var chart = echarts.init(document.getElementById('chart-agents'));
  var agents = __AGENT_NAMES__;
  var values = __AGENT_VALUES__;
  var option = {
    tooltip: { trigger: 'axis', valueFormatter: function(v) { return v.toFixed(1) + '%'; } },
    grid: { left: '12%', right: '8%', bottom: '10%', top: '10%' },
    xAxis: { type: 'category', data: agents, axisLabel: { rotate: 30, fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
    series: [{
      type: 'bar',
      data: values.map(function(v) {
        return { value: v, itemStyle: { color: v >= 70 ? '#27ae60' : v >= 50 ? '#f39c12' : '#e74c3c' } };
      }),
      barMaxWidth: 40,
    }]
  };
  chart.setOption(option);
  window.addEventListener('resize', function() { chart.resize(); });
})();

/* ── Chart 3: Encoding Distribution ── */
(function() {
  var chart = echarts.init(document.getElementById('chart-encoding'));
  var encNames = __ENC_NAMES__;
  var encValues = __ENC_VALUES__;
  var colors = { 'morse': '#2980b9', 'braille': '#8e44ad', 'json': '#95a5a6' };
  var option = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['30%', '70%'],
      center: ['50%', '55%'],
      data: encNames.map(function(n, i) {
        return { name: n, value: encValues[i], itemStyle: { color: colors[n] || '#bdc3c7' } };
      }),
      label: { formatter: '{b}\n{d}%', fontSize: 11 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' } }
    }]
  };
  chart.setOption(option);
  window.addEventListener('resize', function() { chart.resize(); });
})();

/* ── Chart 4: Top Saving Traces ── */
(function() {
  var chart = echarts.init(document.getElementById('chart-topsavers'));
  var topNames = __TOP_NAMES__;
  var topValues = __TOP_VALUES__;
  var option = {
    tooltip: { trigger: 'axis', valueFormatter: function(v) { return v + ' B'; } },
    grid: { left: '25%', right: '8%', bottom: '10%', top: '8%' },
    xAxis: { type: 'value', axisLabel: { formatter: '{value} B' } },
    yAxis: {
      type: 'category',
      data: topNames,
      axisLabel: { fontSize: 9, width: 120, overflow: 'truncate' }
    },
    series: [{
      type: 'bar',
      data: topValues.map(function(v) {
        return { value: v, itemStyle: { color: v > 500 ? '#27ae60' : v > 200 ? '#f39c12' : '#3498db' } };
      }),
      barMaxWidth: 20,
    }]
  };
  chart.setOption(option);
  window.addEventListener('resize', function() { chart.resize(); });
})();

/* ── Table sorting ── */
(function() {
  var table = document.getElementById('trace-table');
  var thead = table.querySelector('thead');
  var tbody = table.querySelector('tbody');
  var sortDir = {};

  thead.addEventListener('click', function(e) {
    var th = e.target.closest('th');
    if (!th) return;
    var col = th.getAttribute('data-col');
    if (!col) return;

    var dir = sortDir[col] === 'asc' ? 'desc' : 'asc';
    sortDir[col] = dir;

    // Clear sort indicators
    thead.querySelectorAll('th').forEach(function(h) {
      h.classList.remove('sort-asc', 'sort-desc');
    });
    th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');

    var rows = Array.from(tbody.querySelectorAll('tr'));
    var colIdx = Array.from(th.parentNode.children).indexOf(th);

    rows.sort(function(a, b) {
      var av = a.children[colIdx] ? a.children[colIdx].textContent.trim() : '';
      var bv = b.children[colIdx] ? b.children[colIdx].textContent.trim() : '';
      var an = parseFloat(av);
      var bn = parseFloat(bv);
      if (!isNaN(an) && !isNaN(bn)) {
        return dir === 'asc' ? an - bn : bn - an;
      }
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });

    rows.forEach(function(r) { tbody.appendChild(r); });
  });
})();
</script>

</body>
</html>"""


def _escape_html(text: str) -> str:
    """Escape text for safe HTML insertion."""
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _build_html(stats: dict) -> str:
    """Fill the HTML template with computed stats."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    traces_dir_str = str(TRACES_DIR)

    total = stats["total_files"]
    pm1_count = stats["pm1_count"]
    json_count = stats["json_count"]
    total_pm1_chars = stats["total_pm1_chars"]
    total_json_bytes = stats["total_json_bytes"]
    savings_pct = stats["savings_pct"]
    json_saved = total_json_bytes - total_pm1_chars
    agent_count = len(stats["per_agent"])

    # Per-agent savings
    agent_names = []
    agent_values = []
    for agent, data in sorted(stats["per_agent"].items()):
        agent_names.append(agent)
        agent_values.append(_compute_savings_pct(data["pm1_chars"], data["json_bytes"]))

    # Daily time series
    ts_dates = list(stats["daily"].keys())
    ts_values = []
    for day in ts_dates:
        d = stats["daily"][day]
        ts_values.append(_compute_savings_pct(d["pm1_chars"], d["json_bytes"]))

    # Encoding distribution
    enc_names = []
    enc_values = []
    for enc, data in sorted(stats["per_encoding"].items()):
        enc_names.append(enc)
        enc_values.append(data["count"])

    # Top savers
    top_names = []
    top_values = []
    for t in stats["top_savers"]:
        fn = t["filename"]
        if len(fn) > 50:
            fn = fn[:47] + "..."
        top_names.append(fn)
        top_values.append(t["savings_bytes"])

    # Detail table rows
    table_rows = []
    for d in stats["detail"]:
        fn = _escape_html(d["filename"])
        date = _escape_html(d["date"])
        agent = _escape_html(d["agent"])
        encoding = _escape_html(d["encoding"])
        json_bytes = str(d["json_bytes"])
        sp = d["savings_pct"]

        if d["encoding"] == "json":
            row_class = ' class="json-row"'
            badge = '<span class="badge none">—</span>'
        elif sp > 0:
            badge = f'<span class="badge save">{sp:.1f}%</span>'
            row_class = ""
        else:
            badge = f'<span class="badge over">{sp:.1f}%</span>'
            row_class = ""

        table_rows.append(
            f'<tr{row_class}>'
            f'<td class="mono">{fn}</td>'
            f'<td>{date}</td>'
            f'<td>{agent}</td>'
            f'<td>{encoding}</td>'
            f'<td class="mono">{json_bytes}</td>'
            f'<td>{badge}</td>'
            f'</tr>'
        )

    # Format large numbers with commas
    def fmt(v):
        return f"{v:,}"

    return (HTML_TEMPLATE
            .replace("__GENERATED__", now)
            .replace("__TRACES_DIR__", _escape_html(traces_dir_str))
            .replace("__TOTAL_FILES__", str(total))
            .replace("__PM1_COUNT__", str(pm1_count))
            .replace("__JSON_COUNT__", str(json_count))
            .replace("__AGENT_COUNT__", str(agent_count))
            .replace("__PM1_CHARS__", fmt(total_pm1_chars))
            .replace("__JSON_SAVED__", fmt(json_saved))
            .replace("__SAVINGS_PCT__", f"{savings_pct:.1f}")
            .replace("__TS_DATES__", json.dumps(ts_dates))
            .replace("__TS_VALUES__", json.dumps(ts_values))
            .replace("__AGENT_NAMES__", json.dumps(agent_names))
            .replace("__AGENT_VALUES__", json.dumps(agent_values))
            .replace("__ENC_NAMES__", json.dumps(enc_names))
            .replace("__ENC_VALUES__", json.dumps(enc_values))
            .replace("__TOP_NAMES__", json.dumps(top_names))
            .replace("__TOP_VALUES__", json.dumps(top_values))
            .replace("__TABLE_ROWS__", "\n".join(table_rows))
            )


def generate_html_report(output_path: str | Path = "pm1-report.html") -> Path:
    """Main entry point. Scan traces, build HTML, write to output_path.

    Args:
        output_path: Path to write the HTML report to.

    Returns:
        The resolved Path of the written report file.
    """
    stats = _scan_traces()
    html = _build_html(stats)
    path = Path(output_path).resolve()
    path.write_text(html, encoding="utf-8")
    print(f"PM-1 dashboard written: {path}")
    print(f"  Files: {stats['total_files']} ({stats['pm1_count']} PM-1, {stats['json_count']} JSON)")
    print(f"  Savings: {stats['savings_pct']}%")
    return path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate PM-1 dashboard HTML")
    parser.add_argument("--output", "-o", default="pm1-report.html",
                        help="Output HTML file path (default: pm1-report.html)")
    args = parser.parse_args()
    generate_html_report(args.output)
