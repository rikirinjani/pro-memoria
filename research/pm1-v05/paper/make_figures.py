import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

out = Path(__file__).resolve().parent / "figures"
out.mkdir(exist_ok=True)

H = np.array([10, 25, 50, 100, 250])
P_cum = np.array([149590, 370703, 737870, 1474888, 3672305])
C_cum = np.array([168676, 633117, 1957375, 6819750, 38366105])
P_ctx = np.array([78.67, 78.63, 78.61, 78.61, 78.60])
C_ctx = np.array([161.81, 396.61, 788.28, 1609.30, 3977.78])
red = np.array([11.32, 41.45, 62.30, 78.37, 90.43])

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})

# Figure 1: cumulative tokens, log scale, with fit curves
fig, ax = plt.subplots(figsize=(4.6, 3.1))
ax.plot(H, P_cum, "o-", color="#1f77b4", label="P (bounded packet)")
ax.plot(H, C_cum, "s-", color="#d62728", label="C (accumulating transcript)")
xs = np.linspace(10, 250, 200)
ax.plot(xs, 14676.770143 * xs + 4192.197598, "--", color="#1f77b4", lw=1, alpha=0.5, label="P linear fit (R\u00b2=0.999998)")
ax.plot(xs, 568.922736 * xs**2 + 11268.721360 * xs - 7709.001538, "--", color="#d62728", lw=1, alpha=0.5, label="C quadratic fit (R\u00b2=0.999999)")
ax.set_xlabel("Horizon (hops)")
ax.set_ylabel("Cumulative tokens")
ax.set_yscale("log")
ax.set_ylim(1e4, 1e8)
ax.legend(fontsize=7, loc="upper left")
ax.set_title("Cumulative token consumption over horizons H10\u2013H250", fontsize=9)
fig.tight_layout()
fig.savefig(out / "fig1_cumulative_tokens.svg", format="svg")
fig.savefig(out / "fig1_cumulative_tokens.png", dpi=300)
plt.close(fig)

# Figure 2: per-hop transmitted context
fig, ax = plt.subplots(figsize=(4.6, 3.1))
ax.plot(H, C_ctx, "s-", color="#d62728", label="C mean per-hop context")
ax.plot(H, P_ctx, "o-", color="#1f77b4", label="P mean per-hop context")
ax.fill_between(H, 78, 79, color="#1f77b4", alpha=0.15, label="P range 78\u201379 tok")
ax.set_xlabel("Horizon (hops)")
ax.set_ylabel("Mean transmitted context (tokens/hop)")
ax.legend(fontsize=7, loc="upper left")
ax.set_title("Per-hop transmitted context: P bounded, C growing", fontsize=9)
fig.tight_layout()
fig.savefig(out / "fig2_per_hop_context.svg", format="svg")
fig.savefig(out / "fig2_per_hop_context.png", dpi=300)
plt.close(fig)

# Figure 3: reduction by horizon
fig, ax = plt.subplots(figsize=(4.6, 3.1))
ax.plot(H, red, "o-", color="#2ca02c")
ax.axhline(90.43, color="#2ca02c", ls=":", lw=1, alpha=0.6)
ax.annotate("H250: 90.43%", xy=(250, 90.43), xytext=(130, 84),
            arrowprops=dict(arrowstyle="->", lw=0.8), fontsize=8)
ax.set_xlabel("Horizon (hops)")
ax.set_ylabel("Cumulative-token reduction 1 \u2212 P/C (%)")
ax.set_ylim(0, 100)
ax.set_title("Reduction relative to accumulating conversational condition", fontsize=9)
fig.tight_layout()
fig.savefig(out / "fig3_reduction.svg", format="svg")
fig.savefig(out / "fig3_reduction.png", dpi=300)
plt.close(fig)

for f in sorted(out.glob("*")):
    print(f.name, f.stat().st_size)
