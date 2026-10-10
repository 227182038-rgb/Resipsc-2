"""Spike-in sensitivity evaluation (validation wrapper)."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from resipsc.config import Config
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.training.spikein import spikein_sweep


def evaluate_spikein_sensitivity(
    model: ResipscEnsemble,
    psc_pool,
    neg_pool,
    ratios: List[float] | None = None,
    replicates: int = 2,
    seed: int = 7,
) -> Dict[str, Any]:
    """Evaluate LOD via PSC spike-in sweep; returns dashboard-friendly dict."""
    cfg = Config()
    if ratios is None:
        ratios = [0.0001, 0.001, 0.01, 0.1, 1.0]
    out = spikein_sweep(
        model, psc_pool, neg_pool,
        ratios=ratios, replicates=replicates, seed=seed,
    )
    # aggregate per ratio for the dashboard line chart
    agg: List[Dict[str, Any]] = []
    by_ratio: Dict[float, List[Dict[str, Any]]] = {}
    for r in out["results"]:
        by_ratio.setdefault(r["ratio"], []).append(r)
    for ratio in sorted(by_ratio):
        reps = by_ratio[ratio]
        agg.append(
            {
                "ratio": ratio,
                "true_pct": float(np.mean([r["true_psc_fraction_pct"] for r in reps])),
                "recall_mean": float(np.mean([r["recall"] for r in reps])),
                "recall_std": float(np.std([r["recall"] for r in reps])),
                "precision_mean": float(np.mean([r["precision"] for r in reps])),
                "estimated_pct_mean": float(np.mean([r["estimated_fraction_pct"] for r in reps])),
                "n_replicates": len(reps),
            }
        )
    out["aggregated"] = agg
    out["wet_lab_reference_lines"] = [
        {"label": "HEC assay LOD", "pct": 0.001},
        {"label": "lncRNA flow LOD", "pct": 0.0001},
        {"label": "Kuroda ddPCR LOD", "pct": 0.01},
        {"label": "In vivo teratoma LOD", "pct": 0.1},
    ]
    return out
