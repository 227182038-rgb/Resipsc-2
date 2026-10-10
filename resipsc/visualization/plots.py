"""matplotlib figures for the publication pipeline (PART 8, Gap 7).

The 6-panel main figure (A-F) at 300 DPI, Helvetica 7pt body / 8pt titles,
180mm width. Colour-blind friendly palette (viridis/cividis family); never
red/green alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MM = 1 / 25.4  # mm -> inch
FIG_WIDTH_IN = 180 * MM
DPI = 300


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "DejaVu Sans", "Arial"],
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "legend.fontsize": 6,
            "figure.dpi": DPI,
            "savefig.dpi": DPI,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
        }
    )


def make_main_figure(
    data: Dict[str, Any],
    out_dir: str = "paper/figures",
    stem: str = "figure_main",
) -> Dict[str, str]:
    """Render the 6-panel publication figure.

    ``data`` keys:
      multisite : list of {label, auc, ci_lower, ci_upper}
      kuroda    : {resipsc_auc, kuroda_auc, delong_p}
      ablation  : list of {name, auc}
      harmony   : {fp_before, fp_after}
      seeds     : list of {seed, auc} + mean/std
      spikein   : list of {true_pct, recall_mean, recall_std}
    """
    _style()
    fig, axes = plt.subplots(
        2, 3, figsize=(FIG_WIDTH_IN, FIG_WIDTH_IN * 0.62), constrained_layout=True
    )
    axA, axB, axC = axes[0]
    axD, axE, axF = axes[1]

    # --- Panel A: multi-site CV ROC-AUC with bootstrap CI bars ---------------
    ms = data.get("multisite", [])
    if ms:
        labels = [m["label"] for m in ms]
        aucs = [m["auc"] for m in ms]
        # asymmetric CI arms, clamped to be non-negative and within [0.5, 1.0]
        lo = [max(0.0, m["auc"] - max(m.get("ci_lower", m["auc"]), 0.5)) for m in ms]
        hi = [max(0.0, min(m.get("ci_upper", m["auc"]), 1.0) - m["auc"]) for m in ms]
        xs = np.arange(len(ms))
        axA.bar(xs, aucs, yerr=[lo, hi], capsize=2, color="#440154", width=0.65,
                error_kw={"elinewidth": 0.7})
        axA.set_xticks(xs)
        axA.set_xticklabels(labels, rotation=35, ha="right")
        axA.set_ylabel("ROC-AUC")
        axA.set_ylim(0.5, 1.02)
        axA.axhline(np.mean(aucs), ls="--", lw=0.7, color="#21918c")
        axA.set_title("A  Multi-site CV (95% bootstrap CI)")
    else:
        axA.text(0.5, 0.5, "A: no data", ha="center")

    # --- Panel B: Kuroda head-to-head + DeLong --------------------------------
    ku = data.get("kuroda", {})
    if ku:
        vals = [ku.get("resipsc_auc", 0), ku.get("kuroda_auc", 0)]
        bars = axB.bar(["resipsc\nensemble", "Kuroda\n3-gene"], vals,
                      color=["#3b528b", "#9bd93c"], width=0.55)
        for b, v in zip(bars, vals):
            axB.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.3f}",
                     ha="center", fontsize=6)
        p = ku.get("delong_p")
        sig = "***" if (p or 1) < 0.001 else "**" if (p or 1) < 0.01 else "*" if (p or 1) < 0.05 else "n.s."
        ymax = max(vals) + 0.06
        axB.plot([0, 0, 1, 1], [ymax - 0.02] * 4, lw=0.7, color="k")
        axB.text(0.5, ymax - 0.015, f"DeLong p = {p:.2g} {sig}", ha="center", fontsize=6)
        axB.set_ylabel("ROC-AUC")
        axB.set_ylim(0.5, 1.05)
        axB.set_title("B  Kuroda head-to-head (DeLong)")
    else:
        axB.text(0.5, 0.5, "B: no data", ha="center")

    # --- Panel C: ablation ------------------------------------------------------
    ab = data.get("ablation", [])
    if ab:
        names = [a["name"] for a in ab][::-1]
        aucs = [a["auc"] for a in ab][::-1]
        ys = np.arange(len(ab))
        axC.barh(ys, aucs, color="#5ec962", height=0.6)
        full = max(aucs)
        axC.axvline(full, ls="--", lw=0.8, color="#440154")
        axC.set_yticks(ys)
        axC.set_yticklabels(names, fontsize=6)
        axC.set_xlabel("ROC-AUC")
        axC.set_xlim(0.5, 1.02)
        axC.set_title("C  Ablation (dashed = full ensemble)")
    else:
        axC.text(0.5, 0.5, "C: no data", ha="center")

    # --- Panel D: Harmony FP before/after ---------------------------------------
    ha = data.get("harmony", {})
    if ha:
        vals = [ha.get("fp_before", 0) * 100, ha.get("fp_after", 0) * 100]
        bars = axD.bar(["before\nHarmony", "after\nHarmony"], vals,
                      color=["#f89540", "#2c728e"], width=0.5)
        for b, v in zip(bars, vals):
            axD.text(b.get_x() + b.get_width() / 2, v + 0.05, f"{v:.2f}%",
                     ha="center", fontsize=6)
        axD.set_ylabel("False-positive rate (%)")
        axD.set_title("D  Batch correction (Harmony)")
    else:
        axD.text(0.5, 0.5, "D: no data", ha="center")

    # --- Panel E: multi-seed reproducibility --------------------------------------
    sd = data.get("seeds", [])
    if sd:
        seeds = [s["seed"] for s in sd]
        aucs = [s["auc"] for s in sd]
        mean, std = float(np.mean(aucs)), float(np.std(aucs))
        axE.errorbar(seeds, aucs, yerr=[std] * len(seeds), fmt="o", ms=3,
                     lw=0.8, capsize=2, color="#440154", ecolor="#90d743")
        axE.axhline(mean, ls="--", lw=0.8, color="#21918c")
        axE.text(0.02, 0.94, f"mean {mean:.3f} ± {std:.3f}", transform=axE.transAxes,
                 fontsize=6, va="top")
        axE.set_xlabel("Random seed")
        axE.set_ylabel("ROC-AUC")
        axE.set_xticks(seeds)
        axE.set_title("E  Multi-seed reproducibility")
    else:
        axE.text(0.5, 0.5, "E: no data", ha="center")

    # --- Panel F: spike-in sensitivity + wet-lab reference lines -------------------
    sp = data.get("spikein", [])
    if sp:
        xs = [s["true_pct"] for s in sp]
        ys = [s["recall_mean"] * 100 for s in sp]
        es = [s.get("recall_std", 0) * 100 for s in sp]
        axF.errorbar(xs, ys, yerr=es, fmt="-o", ms=3, lw=1, capsize=2, color="#3b528b")
        axF.set_xscale("log")
        for pct, lab, c in [
            (0.001, "HEC 0.001%", "#c44e52"),
            (0.0001, "lncRNA 0.0001%", "#dd8452"),
            (0.01, "Kuroda ddPCR 0.01%", "#937860"),
            (0.1, "teratoma 0.1%", "#8172b3"),
        ]:
            axF.axvline(pct, ls=":", lw=0.7, color=c)
            axF.text(pct, 12, lab, rotation=90, fontsize=5, color=c, ha="right")
        axF.set_xlabel("True PSC fraction (%)")
        axF.set_ylabel("Recall (%)")
        axF.set_ylim(0, 108)
        axF.set_title("F  Spike-in sensitivity sweep")
    else:
        axF.text(0.5, 0.5, "F: no data", ha="center")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdf_path = str(out / f"{stem}.pdf")
    png_path = str(out / f"{stem}.png")
    fig.savefig(pdf_path, bbox_inches=None)
    fig.savefig(png_path)
    plt.close(fig)
    return {"pdf": pdf_path, "png": png_path}
