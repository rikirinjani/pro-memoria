"""Generate publication-quality figures for the Pro Memoria paper."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "bench" / "results"

# Load benchmark data
with open(RESULTS / "token_efficiency.json") as f:
    tok_data = json.load(f)

with open(RESULTS / "real_traces.json") as f:
    real_data = json.load(f)

# ── Figure 1: Crucible Trace Benchmark ─────────────────────────────────
def fig1_crucible():
    c = tok_data["crucible"]["cl100k_base"]
    formats = ["Steelman\nJSON", "Hex", "Base64", "Morse\n(DSP)", "AB-1\nBraille"]
    tokens = [c["steelman_json"], c["hex"], c["base64"], c["morse_dsp"], c["braille_dsp"]]
    colors = ['#6b7280', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6']

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(formats, tokens, color=colors, edgecolor='white', linewidth=1.2, width=0.6)

    for bar, val in zip(bars, tokens):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 300,
                f'{val:,}', ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax.set_ylabel('Tokens (cl100k_base)', fontsize=12)
    ax.set_title('Fig. 1: AB-1 Crucible Trace — Token Cost by Format\n(1,417 states, 748 emits, single-byte)', fontsize=13, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.set_ylim(0, max(tokens) * 1.15)

    # Annotation
    ax.annotate('Morse DSP: 84.8%\nsavings vs JSON', xy=(2, c["morse_dsp"]),
                xytext=(0.5, c["morse_dsp"] + 4000),
                arrowprops=dict(arrowstyle='->', color='#f59e0b', lw=1.5),
                fontsize=10, color='#f59e0b', fontweight='bold')

    plt.tight_layout()
    fig.savefig(HERE / "fig1_crucible.png", dpi=200, bbox_inches='tight')
    plt.close()
    print("fig1_crucible.png saved")

# ── Figure 2: Sensitivity Sweep — 128-byte states ──────────────────────
def fig2_sensitivity():
    sweep = tok_data["sensitivity_sweep"]
    change_rates = [10, 30, 50, 70, 90]

    # 128-byte states
    morse_128 = []
    hex_128 = []
    b64_128 = []
    for pct in change_rates:
        key = f"bytes=128_change={pct/100:.0%}"
        e = sweep[key]["cl100k_base"]
        morse_128.append(e["morse_tokens"])
        hex_128.append(e["hex_tokens"])
        b64_128.append(e["base64_tokens"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    # Left: 128-byte sweep
    ax1.plot(change_rates, morse_128, 'o-', color='#f59e0b', linewidth=2.5, markersize=8, label='Morse DSP')
    ax1.plot(change_rates, hex_128, 's--', color='#3b82f6', linewidth=2.5, markersize=8, label='Hex')
    ax1.plot(change_rates, b64_128, '^--', color='#10b981', linewidth=2, markersize=7, label='Base64')
    ax1.axvspan(0, 10, alpha=0.08, color='#f59e0b', label='Morse wins')
    ax1.set_xlabel('State Change Rate (%)', fontsize=12)
    ax1.set_ylabel('Tokens (cl100k_base)', fontsize=12)
    ax1.set_title('128-byte States (500 steps)', fontsize=12, fontweight='bold')
    ax1.legend(fontsize=10, framealpha=0.9)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.set_xticks(change_rates)

    # Right: 8-byte sweep
    morse_8 = []
    hex_8 = []
    for pct in change_rates:
        key = f"bytes=8_change={pct/100:.0%}"
        e = sweep[key]["cl100k_base"]
        morse_8.append(e["morse_tokens"])
        hex_8.append(e["hex_tokens"])

    ax2.plot(change_rates, morse_8, 'o-', color='#f59e0b', linewidth=2.5, markersize=8, label='Morse DSP')
    ax2.plot(change_rates, hex_8, 's--', color='#3b82f6', linewidth=2.5, markersize=8, label='Hex')
    ax2.axvspan(0, 30, alpha=0.08, color='#f59e0b', label='Morse wins')
    ax2.set_xlabel('State Change Rate (%)', fontsize=12)
    ax2.set_ylabel('Tokens (cl100k_base)', fontsize=12)
    ax2.set_title('8-byte States (500 steps)', fontsize=12, fontweight='bold')
    ax2.legend(fontsize=10, framealpha=0.9)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.set_xticks(change_rates)

    fig.suptitle('Fig. 2: Sensitivity Sweep — Morse vs Hex vs Base64 at varying change rates',
                 fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    fig.savefig(HERE / "fig2_sensitivity.png", dpi=200, bbox_inches='tight')
    plt.close()
    print("fig2_sensitivity.png saved")

# ── Figure 3: State Machine Diagram ────────────────────────────────────
def fig3_statemachine():
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis('off')

    states = {
        'CLOSED': (2, 6),
        'HANDSHAKE': (5, 6),
        'SYNCING': (5, 4.5),
        'DATA': (5, 3),
        'ERROR': (8, 3),
        'RECOVERY': (8, 1),
        'DISCONNECT': (2, 1),
    }

    # Draw states as boxes
    for name, (x, y) in states.items():
        color = '#dbeafe' if name != 'ERROR' else '#fecaca'
        border = '#3b82f6' if name != 'ERROR' else '#ef4444'
        box = mpatches.FancyBboxPatch((x-1.2, y-0.4), 2.4, 0.8,
                                        boxstyle="round,pad=0.1",
                                        facecolor=color, edgecolor=border, linewidth=2)
        ax.add_patch(box)
        ax.text(x, y, name, ha='center', va='center', fontsize=11, fontweight='bold')

    # Transitions
    arrows = [
        ('CLOSED', 'HANDSHAKE', 'HELLO'),
        ('HANDSHAKE', 'SYNCING', 'ACK'),
        ('HANDSHAKE', 'DISCONNECT', 'NAK'),
        ('SYNCING', 'DATA', 'ACK'),
        ('SYNCING', 'ERROR', 'ERR'),
        ('DATA', 'ERROR', 'ERR'),
        ('DATA', 'DISCONNECT', 'BYE/HALT'),
        ('ERROR', 'RECOVERY', 'RETRY'),
        ('RECOVERY', 'SYNCING', 'STATE_REP'),
        ('RECOVERY', 'DATA', 'ACK'),
        ('DISCONNECT', 'CLOSED', 'BYE'),
    ]

    for src, dst, label in arrows:
        sx, sy = states[src]
        dx, dy = states[dst]
        ax.annotate('', xy=(dx, dy-0.3), xytext=(sx, sy+0.3),
                    arrowprops=dict(arrowstyle='->', color='#6b7280', lw=1.5,
                                    connectionstyle='arc3,rad=0.2'))
        mx, my = (sx + dx) / 2, (sy + dy) / 2 + 0.3
        ax.text(mx, my, label, ha='center', va='bottom', fontsize=8,
                color='#6b7280', style='italic')

    ax.set_title('Fig. 3: PM-1 Protocol State Machine — 7 states, handshake→sync→data→error→recovery→close',
                 fontsize=12, fontweight='bold', pad=10)
    plt.tight_layout()
    fig.savefig(HERE / "fig3_statemachine.png", dpi=200, bbox_inches='tight')
    plt.close()
    print("fig3_statemachine.png saved")

# ── Figure 4: Real Traces Comparison ───────────────────────────────────
def fig4_realtraces():
    fmts = real_data["formats"]
    labels_map = {
        "Full JSON": "Full JSON",
        "Delta JSON (steelman)": "Delta JSON",
        "Codebook": "Codebook",
        "Base64": "Base64",
        "Hex": "Hex",
        "Morse (raw)": "Morse Raw",
        "Morse (DSP)": "Morse DSP",
        "Braille (DSP)": "AB-1 Braille",
    }
    colors_map = {
        "Full JSON": '#6b7280',
        "Delta JSON (steelman)": '#9ca3af',
        "Codebook": '#059669',
        "Base64": '#10b981',
        "Hex": '#3b82f6',
        "Morse (raw)": '#fbbf24',
        "Morse (DSP)": '#f59e0b',
        "Braille (DSP)": '#8b5cf6',
    }

    labels = []
    tokens_cl = []
    tokens_o2k = []
    colors = []
    for key in labels_map:
        labels.append(labels_map[key])
        tokens_cl.append(fmts[key]["cl100k"])
        tokens_o2k.append(fmts[key]["o200k"])
        colors.append(colors_map[key])

    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = np.arange(len(labels))
    width = 0.35

    bars1 = ax.bar(x - width/2, tokens_cl, width, label='cl100k_base', color=colors, edgecolor='white', linewidth=1)
    bars2 = ax.bar(x + width/2, tokens_o2k, width, label='o200k_base', color=colors, edgecolor='white', linewidth=1, alpha=0.6)

    for bar in bars1:
        val = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, val + 30,
                f'{val:,}', ha='center', va='bottom', fontsize=7, fontweight='bold', color='#374151')

    ax.set_ylabel('Tokens', fontsize=12)
    ax.set_title('Fig. 4: Real Self-Harness Traces — 237 traces, 8-byte states\nMorse DSP: 60.5% savings vs Delta JSON',
                 fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8, rotation=25)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.legend(fontsize=10)

    # Highlight Morse DSP bar
    morse_idx = labels.index("Morse DSP")
    ax.patches[morse_idx].set_edgecolor('#d97706')
    ax.patches[morse_idx].set_linewidth(3)

    plt.tight_layout()
    fig.savefig(HERE / "fig4_realtraces.png", dpi=200, bbox_inches='tight')
    plt.close()
    print("fig4_realtraces.png saved")

# ── Figure 5: Table — Sweep cross-over ─────────────────────────────────
def fig5_crossover_table():
    """Generate a table image showing cross-over points."""
    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.axis('off')

    data = [
        ['State Width', 'Morse wins at', 'Best at high change', 'Note'],
        ['1 byte', 'Never', 'Hex', 'Hex 2 chars/byte always wins'],
        ['8 bytes', '≤30% change', 'Hex/Base64', 'Agent sweet spot'],
        ['32 bytes', '≤10% change', 'Hex/Base64', 'Cross-over shifts left'],
        ['128 bytes', '≤10% change', 'Hex/Base64', 'Morse 1.8× better at 10%'],
    ]

    table = ax.table(cellText=data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)

    for i in range(5):
        for j in range(4):
            cell = table[i, j]
            if i == 0:
                cell.set_facecolor('#1e3a5f')
                cell.set_text_props(color='white', fontweight='bold')
            elif j == 1 and '≤' in data[i][j]:
                cell.set_facecolor('#fef3c7')
            elif j == 1 and 'Never' in data[i][j]:
                cell.set_facecolor('#fecaca')

    ax.set_title('Table 1: Morse vs Hex — Cross-over by State Width',
                 fontsize=12, fontweight='bold', pad=10)
    plt.tight_layout()
    fig.savefig(HERE / "fig5_crossover.png", dpi=200, bbox_inches='tight')
    plt.close()
    print("fig5_crossover.png saved")


if __name__ == "__main__":
    fig1_crucible()
    fig2_sensitivity()
    fig3_statemachine()
    fig4_realtraces()
    fig5_crossover_table()
    print("\nAll figures generated.")
