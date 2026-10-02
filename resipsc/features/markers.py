"""Biomarker cross-check: OCT4(POU5F1)/NANOG/SOX2 and extended panel scoring."""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

# Canonical pluripotency markers used for the orthogonal biomarker check.
CORE_MARKERS = ["POU5F1", "NANOG", "SOX2"]
EXTENDED_MARKERS = ["LIN28A", "KLF4", "MYC", "ZFP42", "ESRG"]
ALL_MARKERS = CORE_MARKERS + EXTENDED_MARKERS

# Lineage markers for germ-layer assignment
LINEAGE_MARKERS: Dict[str, List[str]] = {
    "ectoderm": ["PAX6", "NES", "DCX", "MAP2", "TUBB3", "SOX1", "GFAP"],
    "mesoderm": ["TBXT", "MESP1", "NKX2-5", "TNNT2", "MYH6", "ACTA2", "DES", "MYOD1"],
    "endoderm": ["SOX17", "FOXA2", "GATA4", "GATA6", "HNF4A", "PDX1", "AFP", "ALB"],
}


def _gene_means(a, genes: List[str]) -> Dict[str, float]:
    """Mean log-normalised expression of each gene across cells."""
    X = a.X
    try:
        import scipy.sparse as sp

        if sp.issparse(X):
            X = np.asarray(X.todense())
    except Exception:  # noqa: BLE001
        pass
    X = np.asarray(X)
    means = X.mean(axis=0) if X.shape[0] else np.array([])
    lookup = {g: float(means[i]) for i, g in enumerate(a.var_names)}
    return {g: lookup.get(g, 0.0) for g in genes}


def _gene_matrix(a, genes: List[str]):
    """Return (cells x genes) matrix for available genes plus presence mask."""
    X = a.X
    try:
        import scipy.sparse as sp

        if sp.issparse(X):
            X = np.asarray(X.todense())
    except Exception:  # noqa: BLE001
        pass
    X = np.asarray(X)
    var_list = list(a.var_names)
    cols, kept = [], []
    for g in genes:
        if g in var_list:
            cols.append(X[:, var_list.index(g)])
            kept.append(g)
    if cols:
        M = np.stack(cols, axis=1)
    else:
        M = np.zeros((X.shape[0], 0))
    return M, kept


def pluripotency_score(a) -> np.ndarray:
    """Per-cell pluripotency score: mean log-expression of core markers.

    Returns an array in [0, ~8] (log1p CPM scale). Cells with no detectable
    core markers score 0.
    """
    M, _ = _gene_matrix(a, CORE_MARKERS)
    if M.shape[1] == 0:
        M, _ = _gene_matrix(a, ALL_MARKERS)
    if M.shape[1] == 0:
        return np.zeros(a.n_obs)
    return M.mean(axis=1)


def biomarker_summary(a) -> Dict[str, float]:
    """Dataset-level summary of marker expression (mean across all cells)."""
    means = _gene_means(a, ALL_MARKERS)
    core_vals = [means.get(g, 0.0) for g in CORE_MARKERS]
    return {
        **{f"mean_{g}": means.get(g, 0.0) for g in ALL_MARKERS},
        "core_marker_mean": float(np.mean(core_vals)) if core_vals else 0.0,
        "core_detected": int(sum(v > 0.5 for v in core_vals)),
        "n_marker_genes_present": int(sum(1 for g in ALL_MARKERS if g in set(a.var_names))),
    }


def lineage_marker_scores(a) -> Dict[str, np.ndarray]:
    """Per-cell marker score per germ layer (mean log-expression)."""
    out = {}
    for lineage, genes in LINEAGE_MARKERS.items():
        M, _ = _gene_matrix(a, genes)
        out[lineage] = M.mean(axis=1) if M.shape[1] else np.zeros(a.n_obs)
    return out


def assign_lineage(a, psc_mask: np.ndarray) -> np.ndarray:
    """Assign each cell a lineage label.

    PSC-predicted cells are labelled 'pluripotent'; others get the germ layer
    with the highest mean marker score.
    """
    scores = lineage_marker_scores(a)
    layers = list(scores.keys())
    S = np.stack([scores[k] for k in layers], axis=1)
    best = np.array(layers, dtype=object)[np.argmax(S, axis=1)]
    labels = best.astype(object)
    labels[psc_mask] = "pluripotent"
    return labels
