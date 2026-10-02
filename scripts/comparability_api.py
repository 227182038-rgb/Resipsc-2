#!/usr/bin/env python3
"""comparability_api.py — ICH Q5E comparability run for the API route.

Compares the current production model (results/final_model.pkl) against a
candidate model. If --old/--new paths are given they are used; otherwise the
candidate is freshly trained with seed 123 (a realistic promotion-gate demo).

Usage:
  python scripts/comparability_api.py [--old PATH] [--new PATH] [--train-candidate]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.metrics import roc_auc_score

from resipsc.compliance.audit import AuditTrail
from resipsc.compliance.comparability_report import build_comparability_report
from resipsc.config import default_config
from resipsc.data.synthetic import simulate_datasets
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.pipeline import build_training_matrix
from resipsc.utils.io import load_pickle, save_pickle
from resipsc.utils.logging import get_logger
from resipsc.utils.seed import seed_everything

LOGGER = get_logger("comparability_api")


def golden_dataset():
    """Frozen golden evaluation corpus (same seeds every time)."""
    seed_everything(42)
    cfg = default_config()
    ads = simulate_datasets(max_cells_per_dataset=cfg.max_cells_per_dataset, seed=42)
    return ads, cfg


def featurize_all(model, ads):
    Xs, ys = [], []
    for a in ads:
        X, _ = model.featurize(a)
        Xs.append(X)
        ys.append(a.obs["is_psc"].values.astype(int))
    return np.vstack(Xs), np.concatenate(ys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="results/final_model.pkl")
    ap.add_argument("--new", default=None)
    ap.add_argument("--train-candidate", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    ads, cfg = golden_dataset()

    old_model = load_pickle(args.old)
    new_path = args.new
    if new_path and os.path.exists(new_path):
        new_model = load_pickle(new_path)
    else:
        # train a realistic candidate with a different seed
        LOGGER.info("training candidate model (seed 123) for comparability")
        X, y, genes, mu, sd, sites = build_training_matrix(ads, n_hvg=cfg.n_hvg)
        cand_cfg = default_config()
        cand_cfg.random_state = 123
        seed_everything(123)
        new_model = ResipscEnsemble(cand_cfg)
        new_model.fit(X, y, gene_names=genes, mu=mu, sd=sd)
        new_model.quantification = dict(getattr(old_model, "quantification") or {})
        os.makedirs("results/candidates", exist_ok=True)
        new_path = "results/candidates/candidate_seed123.pkl"
        save_pickle(new_model, new_path)

    Xg, yg = featurize_all(old_model, ads)
    p_old = old_model.predict_proba(Xg)[:, 1]
    p_new = new_model.predict_proba(Xg)[:, 1]

    from resipsc.validation.comparability import ComparabilityEngine

    ce = ComparabilityEngine()
    comparison = ce.compare(
        yg, p_old, p_new,
        old_version=f"resipsc@{os.path.getmtime(args.old):.0f}",
        new_version=f"candidate@{os.path.getmtime(new_path):.0f}",
    )
    comparison["old_model_path"] = args.old
    comparison["new_model_path"] = new_path
    comparison["old_auc"] = round(float(roc_auc_score(yg, p_old)), 4)
    comparison["new_auc"] = round(float(roc_auc_score(yg, p_new)), 4)
    comparison["golden_n"] = int(len(yg))
    comparison["runtime_seconds"] = round(time.time() - t0, 1)
    report = build_comparability_report(comparison, out_dir="results")

    trail = AuditTrail()
    trail.log("comparability_study", "model", os.path.basename(new_path),
              new_value={"verdict": comparison["verdict"],
                         "kappa": comparison["cohens_kappa"],
                         "sens_delta": comparison["sensitivity_delta"]},
              reason="ICH Q5E promotion gate", user_id="qa_officer")

    print(json.dumps({"status": "ok", "comparison": comparison, "report": report}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
