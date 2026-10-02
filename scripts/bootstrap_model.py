#!/usr/bin/env python3
"""bootstrap_model.py — fast synthetic-only model (fallback when pbmc3k absent)."""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resipsc.config import Config
from resipsc.data.synthetic import simulate_datasets
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.pipeline import build_training_matrix
from resipsc.utils.io import save_pickle
from resipsc.utils.seed import seed_everything


def main() -> int:
    t0 = time.time()
    seed_everything(42)
    cfg = Config(n_hvg=300, max_cells_per_dataset=300, xgb_n_estimators=40,
                 rf_n_estimators=40, skip_transformer=True, spikein_replicates=1)
    ads = simulate_datasets(max_cells_per_dataset=300, seed=42)
    X, y, genes, mu, sd, sites = build_training_matrix(ads, n_hvg=cfg.n_hvg)
    model = ResipscEnsemble(cfg)
    model.fit(X, y, gene_names=genes, mu=mu, sd=sd)
    model.train_info["training_data"] = "synthetic multi-site only (bootstrap)"
    os.makedirs("results", exist_ok=True)
    save_pickle(model, "results/final_model.pkl")
    print(f"OK bootstrap model saved ({time.time()-t0:.1f}s, {X.shape[0]} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
