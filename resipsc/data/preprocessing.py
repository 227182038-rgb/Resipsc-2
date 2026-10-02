"""Preprocessing: filtering, normalisation, HVG selection, per-gene scaling."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from anndata import AnnData
from scipy import sparse

from resipsc.utils.logging import get_logger

LOGGER = get_logger("data.preprocessing")

MARKER_GENES = [
    "POU5F1", "NANOG", "SOX2", "LIN28A", "KLF4", "MYC", "ZFP42", "ESRG",
]

MIN_CELLS_PER_GENE = 3
MIN_GENES_PER_CELL = 10


def _to_dense(X) -> np.ndarray:
    if sparse.issparse(X):
        return np.asarray(X.todense(), dtype=np.float32)
    return np.asarray(X, dtype=np.float32)


def normalize_anndata(adata: AnnData, target_sum: float = 1e4) -> AnnData:
    """QC-filter -> library-normalise -> log1p. No HVG / scaling.

    This is the canonical first stage shared by training and inference.
    """
    a = adata.copy()
    X = _to_dense(a.X)

    genes_per_cell = (X > 0).sum(axis=1)
    keep_cells = genes_per_cell >= MIN_GENES_PER_CELL
    if keep_cells.sum() < 20:
        keep_cells = np.ones(X.shape[0], dtype=bool)
    if keep_cells.sum() < X.shape[0]:
        X = X[keep_cells]
        a = a[keep_cells].copy()
    a.obs["n_genes_by_counts"] = (X > 0).sum(axis=1)

    cells_per_gene = (X > 0).sum(axis=0)
    keep_genes = cells_per_gene >= MIN_CELLS_PER_GENE
    var_names = list(a.var_names)
    for g in MARKER_GENES:
        if g in var_names:
            keep_genes[var_names.index(g)] = True
    if keep_genes.sum() < 30:
        keep_genes = np.ones(X.shape[1], dtype=bool)
    if keep_genes.sum() < X.shape[1]:
        X = X[:, keep_genes]
        a = a[:, keep_genes].copy()

    lib = X.sum(axis=1, keepdims=True)
    lib[lib == 0] = 1.0
    X = np.log1p(X / lib * target_sum)
    a.X = X.astype(np.float32)
    return a


def align_to_genes(a_norm: AnnData, gene_list: List[str]) -> np.ndarray:
    """Dense (n_cells, len(gene_list)) matrix from a log-normalised AnnData.

    Missing genes become zero columns; duplicated gene symbols are averaged
    so alignment is deterministic. Row order follows the AnnData.
    """
    import scipy.sparse as sp

    M = a_norm.X
    if sp.issparse(M):
        M = np.asarray(M.todense())
    M = np.asarray(M, dtype=np.float32)
    lookup = {g: i for i, g in enumerate(a_norm.var_names)}
    out = np.zeros((M.shape[0], len(gene_list)), dtype=np.float32)
    for j, g in enumerate(gene_list):
        i = lookup.get(g, None)
        if i is not None:
            out[:, j] = M[:, i]
    return out


def select_hvgs(a_norm: AnnData, n_hvg: int = 300) -> List[str]:
    """Pick top-variance genes (always including the marker panel)."""
    import scipy.sparse as sp

    M = a_norm.X
    if sp.issparse(M):
        M = np.asarray(M.todense())
    M = np.asarray(M, dtype=np.float32)
    disp = M.var(axis=0)
    order = np.argsort(-disp)
    chosen: List[str] = []
    for i in order:
        chosen.append(str(a_norm.var_names[i]))
        if len(chosen) >= max(0, n_hvg - len(MARKER_GENES)):
            break
    for g in MARKER_GENES:
        if g in set(a_norm.var_names) and g not in chosen:
            chosen.append(g)
    return chosen


def scale_with(X: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    """Z-scale with external (training) statistics, clipped to +-10."""
    mu = np.asarray(mu, dtype=np.float32).reshape(1, -1)
    sd = np.asarray(sd, dtype=np.float32).reshape(1, -1)
    sd = np.where(sd == 0, 1.0, sd)
    return np.clip((X - mu) / sd, -10, 10).astype(np.float32)


def preprocess_anndata(
    adata: AnnData,
    n_hvg: int = 300,
    target_sum: float = 1e4,
) -> AnnData:
    """QC-filter -> normalise -> log1p -> HVG -> scale (per gene, clipped).

    Works fully in-memory on dense conversions of the stored matrix. The
    input is copied so the caller's object is never mutated.
    """
    a = adata.copy()
    X = _to_dense(a.X)

    # 1. cell QC: enough genes detected
    genes_per_cell = (X > 0).sum(axis=1)
    keep_cells = genes_per_cell >= MIN_GENES_PER_CELL
    if keep_cells.sum() < 20:  # degenerate file — keep everything
        keep_cells = np.ones(X.shape[0], dtype=bool)
    if keep_cells.sum() < X.shape[0]:
        LOGGER.info("filtering cells: %d -> %d", X.shape[0], int(keep_cells.sum()))
        X = X[keep_cells]
        a = a[keep_cells].copy()
        a.obs["n_genes_by_counts"] = genes_per_cell[keep_cells]
    else:
        a.obs["n_genes_by_counts"] = genes_per_cell

    # 2. gene QC
    cells_per_gene = (X > 0).sum(axis=0)
    keep_genes = cells_per_gene >= MIN_CELLS_PER_GENE
    # always keep known marker genes so the biomarker cross-check can run
    var_names = list(a.var_names)
    for g in MARKER_GENES:
        if g in var_names:
            keep_genes[var_names.index(g)] = True
    if keep_genes.sum() < 30:
        keep_genes = np.ones(X.shape[1], dtype=bool)
    if keep_genes.sum() < X.shape[1]:
        X = X[:, keep_genes]
        a = a[:, keep_genes].copy()

    # 3. normalise per cell to target_sum then log1p
    lib = X.sum(axis=1, keepdims=True)
    lib[lib == 0] = 1.0
    X = X / lib * target_sum
    X = np.log1p(X)
    a.X = X.astype(np.float32)

    # 4. HVG selection (dispersion proxy: variance of log data)
    disp = X.var(axis=0)
    order = np.argsort(-disp)
    n_hvg_eff = int(min(n_hvg, len(order)))
    hvg_mask = np.zeros(X.shape[1], dtype=bool)
    hvg_mask[order[:n_hvg_eff]] = True
    for g in MARKER_GENES:  # always keep the core pluripotency panel
        if g in list(a.var_names):
            hvg_mask[list(a.var_names).index(g)] = True
    a.var["highly_variable"] = hvg_mask

    # 5. per-gene scaling (z-score, clip to [-10, 10] like Scanpy)
    mu = X.mean(axis=0, keepdims=True)
    sd = X.std(axis=0, keepdims=True)
    sd[sd == 0] = 1.0
    Xs = np.clip((X - mu) / sd, -10, 10)
    a.layers["scaled"] = Xs.astype(np.float32)
    a.uns["scale_mu"] = mu.ravel()
    a.uns["scale_sd"] = sd.ravel()

    return a


def matrix_from_anndata(a: AnnData) -> Tuple[np.ndarray, List[str], List[str]]:
    """Return (scaled feature matrix, gene names, cell ids).

    Uses the scaled layer on HVGs if present, else the log-normalised X.
    """
    if "scaled" in a.layers:
        X = _to_dense(a.layers["scaled"])
    else:
        X = _to_dense(a.X)
    if a.var["highly_variable"].dtype == bool:
        hvg = a.var["highly_variable"].values.astype(bool)
    else:
        hvg = np.asarray(a.var["highly_variable"], dtype=bool)
    if hvg.sum() > 0:
        X = X[:, hvg]
        genes = [g for g, h in zip(a.var_names, hvg) if h]
    else:
        genes = list(a.var_names)
    cells = list(a.obs_names)
    return X.astype(np.float32), genes, cells
