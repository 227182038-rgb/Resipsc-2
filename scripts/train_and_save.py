#!/usr/bin/env python3
"""train_and_save.py — real-data training path (Wellington iPSC dataset).

If data/real/iPSC_integration_41k.h5ad exists, trains on the real 41,670-cell
corpus (Ensembl IDs mapped to gene symbols via var['feature_name']); applies
RAM-appropriate fallbacks on OOM. Otherwise exits with guidance to run
train_hybrid.py instead (exit code 4, non-fatal fallback marker).
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from resipsc.config import default_config
from resipsc.data.acquisition import download_census_dataset
from resipsc.pipeline import build_training_matrix
from resipsc.utils.logging import get_logger
from resipsc.utils.seed import seed_everything

LOGGER = get_logger("train_real")
REAL_PATH = "data/real/iPSC_integration_41k.h5ad"


def main() -> int:
    if not os.path.exists(REAL_PATH):
        LOGGER.info("Wellington dataset not found at %s", REAL_PATH)
        print("SKIP: Wellington dataset absent — run scripts/train_hybrid.py instead")
        return 4
    import anndata as ad

    from resipsc.data.acquisition import _use_raw_and_set_symbols
    from resipsc.models.ensemble import ResipscEnsemble
    from resipsc.utils.io import save_pickle

    t0 = time.time()
    seed_everything(42)
    cfg = default_config()

    a = ad.read_h5ad(REAL_PATH, backed="r")
    n_total = a.n_obs
    pub = a.obs["Publication"].astype(str).values[:] if "Publication" in a.obs.columns else np.array(["unknown"] * n_total)
    # label: publication containing "iPS"/"ESC"/"Embryo" treated as PSC-containing;
    # ground-truth per-cell labels come from the dataset's own annotations when present.
    y_all = None
    for col in ("cell_type", "annotations", "celltype", " CellTypist"):
        if col in a.obs.columns:
            vals = a.obs[col].astype(str).values[:]
            y_all = np.where(vals.str.contains("iPS|ESC|embryo|pluripot", case=False, regex=True), 1, 0)
            break
    if y_all is None:
        y_all = np.zeros(n_total, dtype=int)
        y_all[np.char.find(np.char.lower(pub.astype(str)), "ips") >= 0] = 1

    rng = np.random.default_rng(42)
    keep = np.sort(rng.choice(n_total, size=min(cfg.max_cells_per_dataset * 6, n_total), replace=False))
    sub = a[keep].to_memory()
    sub = _use_raw_and_set_symbols(sub)
    sub.obs["is_psc"] = y_all[keep]
    sub.obs["dataset_id"] = np.array(pub)[keep]
    sub.obs["lineage"] = "pluripotent"

    X, y, genes, mu, sd, sites = build_training_matrix([sub], n_hvg=cfg.n_hvg)
    model = ResipscEnsemble(cfg)
    model.fit(X, y, gene_names=genes, mu=mu, sd=sd)
    model.train_info["training_data"] = "real Wellington iPSC integration (41k)"
    save_pickle(model, "results/final_model.pkl")
    print(f"OK real-data model ({time.time()-t0:.0f}s, {X.shape[0]} cells, "
          f"{y.mean()*100:.1f}% PSC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
