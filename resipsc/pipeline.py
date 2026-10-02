"""Pipeline orchestrator: data -> features -> model -> report."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from resipsc.config import Config
from resipsc.data.preprocessing import (
    align_to_genes,
    normalize_anndata,
    scale_with,
    select_hvgs,
)
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.utils.logging import get_logger
from resipsc.utils.seed import seed_everything

LOGGER = get_logger("pipeline")


def build_training_matrix(
    adatas,
    n_hvg: int = 300,
) -> Tuple[np.ndarray, np.ndarray, List[str], np.ndarray, np.ndarray, np.ndarray]:
    """Normalise datasets, select HVGs from the reference, scale.

    HVGs are selected from the FIRST dataset (the synthetic reference corpus)
    and every other dataset is aligned to that gene list — genes absent from
    a dataset become zero columns, which is biologically true (a PBMC does
    not express a synthetic-only gene). Using alignment instead of a strict
    intersection keeps the full feature space for hybrid corpora where the
    real reference shares only marker genes with the synthetic universe.

    Returns (X_scaled, y, gene_list, mu, sd, site_labels).
    ``mu``/``sd`` are the training statistics the model must reuse at
    inference time to featurise new files.
    """
    normed = [normalize_anndata(a) for a in adatas]
    gene_list = select_hvgs(normed[0], n_hvg=n_hvg)

    Xs, ys, sites = [], [], []
    for a in normed:
        Xs.append(align_to_genes(a, gene_list))
        y = a.obs["is_psc"].values.astype(int) if "is_psc" in a.obs else np.zeros(a.n_obs, int)
        ys.append(y)
        sites.append(
            a.obs["dataset_id"].values.astype(str)
            if "dataset_id" in a.obs
            else np.array(["unknown"] * a.n_obs)
        )
    X = np.vstack(Xs)
    y = np.concatenate(ys)
    sites = np.concatenate(sites)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs_scaled = scale_with(X, mu, sd)
    return Xs_scaled, y, gene_list, mu, sd, sites


def run_pipeline(
    adatas,
    config: Config | None = None,
    prev_batches: Optional[List[Dict[str, Any]]] = None,
    batch_id: str = "BATCH-000",
    input_file: str = "simulated.h5ad",
) -> Dict[str, Any]:
    """Train on the given datasets and return a full QC report on holdout.

    Fits the ensemble on the concatenation of ``adatas`` (labels from
    obs['is_psc']) and emits a QC report on the last dataset so downstream
    tooling can exercise the report path.
    """
    config = config or Config()
    seed_everything(config.seed)

    X, y, gene_list, mu, sd, _sites = build_training_matrix(adatas, n_hvg=config.n_hvg)
    held_out = adatas[-1]

    model = ResipscEnsemble(config)
    model.fit(X, y, gene_names=gene_list, mu=mu, sd=sd)

    report = model.qc_report_dict(
        held_out,
        batch_id=batch_id,
        input_file=input_file,
        prev_batches=prev_batches,
    )
    from resipsc.utils.io import save_pickle

    save_pickle(model, str(_results_path(config) / "final_model.pkl"))
    return report


def _results_path(config: Config):
    from pathlib import Path

    p = Path(config.results_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p
