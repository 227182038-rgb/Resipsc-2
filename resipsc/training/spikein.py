"""Spike-in sensitivity sweep: inject PSCs at known fractions and measure recall."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from resipsc.config import Config
from resipsc.data.preprocessing import matrix_from_anndata, preprocess_anndata
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.utils.logging import get_logger

LOGGER = get_logger("training.spikein")


def spikein_sweep(
    model: ResipscEnsemble,
    psc_pool_adata,
    neg_pool_adata,
    ratios: List[float] | None = None,
    replicates: int = 2,
    n_base_cells: int = 2000,
    seed: int = 7,
) -> Dict[str, Any]:
    """Evaluate detection recall at decreasing PSC spike-in fractions.

    ``psc_pool_adata`` / ``neg_pool_adata`` are AnnData objects of pure PSC /
    differentiated cells. For each ratio r in ``ratios`` and each replicate,
    build a mixture of ``n_base_cells`` negatives + ``r*n_base_cells`` PSCs,
    score with the frozen model and record recall / precision / estimated
    fraction.
    """
    ratios = ratios or list(Config().spikein_ratios)
    rng = np.random.default_rng(seed)

    neg_p = preprocess_anndata(neg_pool_adata, n_hvg=Config().n_hvg)
    psc_p = preprocess_anndata(psc_pool_adata, n_hvg=Config().n_hvg)
    Xn, _, _ = matrix_from_anldata_safe(neg_p)
    Xp, _, _ = matrix_from_anldata_safe(psc_p)
    w = min(Xn.shape[1], Xp.shape[1])
    Xn, Xp = Xn[:, :w], Xp[:, :w]

    results: List[Dict[str, Any]] = []
    for ratio in ratios:
        n_psc = max(1, int(round(ratio * n_base_cells)))
        if n_psc > Xp.shape[0]:
            n_psc = Xp.shape[0]
        for rep in range(replicates):
            neg_idx = rng.choice(Xn.shape[0], size=min(n_base_cells, Xn.shape[0]), replace=False)
            psc_idx = rng.choice(Xp.shape[0], size=n_psc, replace=n_psc > Xp.shape[0])
            X = np.vstack([Xn[neg_idx], Xp[psc_idx]])
            y = np.concatenate([np.zeros(len(neg_idx)), np.ones(n_psc)])
            p = model.predict_proba(X)[:, 1]
            yhat = (p >= 0.5).astype(int)
            tp = int(((y == 1) & (yhat == 1)).sum())
            fn = int(((y == 1) & (yhat == 0)).sum())
            fp = int(((y == 0) & (yhat == 1)).sum())
            recall = tp / max(1, tp + fn)
            precision = tp / max(1, tp + fp)
            est_frac = float(yhat.mean())
            true_frac = float(y.mean())
            results.append(
                {
                    "ratio": ratio,
                    "true_psc_fraction_pct": 100.0 * true_frac,
                    "n_psc_spiked": n_psc,
                    "n_cells": int(len(y)),
                    "replicate": rep + 1,
                    "recall": recall,
                    "precision": precision,
                    "estimated_fraction_pct": 100.0 * est_frac,
                    "detected_psc": tp,
                }
            )
            LOGGER.info(
                "spike-in %.4f%% rep %d: recall %.3f, est %.4f%%",
                100 * true_frac, rep + 1, recall, 100 * est_frac,
            )

    # limit of detection (smallest ratio with mean recall >= 0.9)
    lod = None
    by_ratio: Dict[float, List[float]] = {}
    for r in results:
        by_ratio.setdefault(r["ratio"], []).append(r["recall"])
    for ratio in sorted(by_ratio):
        if float(np.mean(by_ratio[ratio])) >= 0.9:
            lod = ratio
            break
    return {
        "scheme": "PSC spike-in sensitivity sweep",
        "results": results,
        "limit_of_detection_fraction": lod,
        "headline": (
            f"Spike-in LOD {100*lod:.4f}% at recall>=0.9" if lod else
            "LOD below evaluated range — see per-ratio recall"
        ),
        "wet_lab_reference": {
            "HEC_assay_pct": 0.001,
            "lncRNA_flow_pct": 0.0001,
            "ddPCR_Kuroda_pct": 0.01,
        },
    }


def matrix_from_anldata_safe(a):  # small alias to avoid circular import
    return matrix_from_anndata(a)
