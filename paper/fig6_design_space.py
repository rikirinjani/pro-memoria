"""Generate Figure 6: Design Space Map — Machine-Native Communication Systems."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ── Data points ──────────────────────────────────────────────────────
systems = [
    # (label, x, y, color, marker)
    ("PM-1",        0.15, 0.85, '#f59e0b', 'o'),
    ("AB-1",        0.10, 0.90, '#8b5cf6', 'o'),
    ("Codebook",    0.20, 0.80, '#059669', 'o'),
    ("Hex",         0.25, 0.75, '#3b82f6', 'o'),
    ("BabelTele",   0.75, 0.20, '#ef4444', 'o'),
    ("Delta JSON",  0.30, 0.65, '#9ca3af', 'o'),
]

fig, ax = plt.subplots(figsize=(9, 7))

# Plot each system
for label, x, y, color, marker in systems:
    ax.scatter(x, y, s=200, c=color, marker=marker, edgecolors='#374151',
               linewidths=1.5, zorder=5)
    # Offset label slightly
    offset_x = 0.02
    offset_y = 0.02
    if label == "PM-1":
        offset_x = -0.01
        offset_y = 0.035
    elif label == "AB-1":
        offset_x = -0.03
        offset_y = 0.035
    elif label == "Hex":
        offset_y = -0.035
    elif label == "Delta JSON":
        offset_y = -0.035
        offset_x = 0.03
    elif label == "BabelTele":
        offset_x = 0.03
        offset_y = 0.03
    ax.annotate(label, (x, y), xytext=(x + offset_x, y + offset_y),
                fontsize=11, fontweight='bold', color=color,
                ha='left', va='bottom')

# ── Grid and axes ────────────────────────────────────────────────────
ax.set_xlim(-0.05, 1.05)
ax.set_ylim(-0.05, 1.05)
ax.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
ax.grid(True, linestyle=':', alpha=0.5)
ax.set_xlabel('Target Domain', fontsize=13, fontweight='bold')
ax.set_ylabel('Recovery Guarantee', fontsize=13, fontweight='bold')
ax.set_title('Figure 6: Design Space — Machine-Native Communication Systems',
             fontsize=14, fontweight='bold', pad=12)

# ── Quadrant labels ──────────────────────────────────────────────────
ax.text(0.5, 1.02, 'Exact / Deterministic Recovery',
        ha='center', va='bottom', fontsize=11, fontweight='bold',
        color='#1e3a5f', transform=ax.get_xaxis_transform())
ax.text(0.5, -0.06, 'Semantic / Learned Recovery',
        ha='center', va='top', fontsize=11, fontweight='bold',
        color='#6b7280', transform=ax.get_xaxis_transform())
ax.text(-0.06, 0.5, 'Structured State',
        ha='right', va='center', fontsize=11, fontweight='bold',
        color='#1e3a5f', rotation=90, transform=ax.get_yaxis_transform())
ax.text(1.06, 0.5, 'Natural Language',
        ha='left', va='center', fontsize=11, fontweight='bold',
        color='#6b7280', rotation=90, transform=ax.get_yaxis_transform())

# ── Quadrant shading (subtle) ────────────────────────────────────────
# Top-left: Exact + Structured — PM-1/AB-1 territory
ax.axhspan(0.0, 1.0, 0.0, 0.5, alpha=0.04, color='#3b82f6')
# Bottom-right: Semantic + Language — BabelTele territory
ax.axhspan(0.0, 1.0, 0.5, 1.0, alpha=0.04, color='#ef4444')

# ── Descriptive callouts ─────────────────────────────────────────────
ax.annotate('PM-1 / AB-1\nStructured,\nExact recovery',
            xy=(0.15, 0.87), xytext=(-0.02, 0.87),
            fontsize=8, color='#f59e0b', fontstyle='italic',
            ha='right', va='center',
            arrowprops=dict(arrowstyle='->', color='#f59e0b', lw=0.8,
                            connectionstyle='arc3,rad=0.0'))

ax.annotate('Babel Telepasta\nNatural language,\nSemantic recovery',
            xy=(0.75, 0.20), xytext=(1.02, 0.20),
            fontsize=8, color='#ef4444', fontstyle='italic',
            ha='left', va='center',
            arrowprops=dict(arrowstyle='->', color='#ef4444', lw=0.8,
                            connectionstyle='arc3,rad=0.0'))

plt.tight_layout()
fig.savefig(HERE / "fig6_design_space.png", dpi=200, bbox_inches='tight')
plt.close()
print("fig6_design_space.png saved")
