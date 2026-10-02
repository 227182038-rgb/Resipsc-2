"""Benchmarking: multi-site CV, cross-lineage CV.

Multi-site CV: leave-one-publication-out (LOPO) — train on all but one
simulated site, test on the held-out site. Cross-lineage CV: train on two
germ layers, test on the held-out layer (generalisation stress test).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from resipsc.config import Config
from resipsc.data.preprocessing import matrix_from_anndata, preprocess_anndata
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.utils.logging import get_logger

LOGGER = get_logger("training.benchmark")


def _metrics(y_true: np.ndarray, p: np.ndarray) -> Dict[str, float]:
    yhat = (p >= 0.5).astype(int)
    out: Dict[str, float] = {}
    try:
        out["roc_auc"] = float(roc_auc_score(y_true, p))
    except Exception:  # noqa: BLE001 - single-class fold
        out["roc_auc"] = float("nan")
    try:
        out["pr_auc"] = float(average_precision_score(y_true, p))
    except Exception:  # noqa: BLE001
        out["pr_auc"] = float("nan")
    out["sensitivity"] = float(recall_score(y_true, yhat, zero_division=0))
    out["specificity"] = float(
        recall_score(1 - y_true, 1 - yhat, zero_division=0)
    )
    out["precision"] = float(precision_score(y_true, yhat, zero_division=0))
    return out


def _prep(adatas) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Concatenate preprocessed AnnData objects into X, y, site labels."""
    Xs, ys, sites = [], [], []
    for a in adatas:
        ap = preprocess_anndata(a, n_hvg=Config().n_hvg)
        X, _, _ = matrix_from_anndata(ap)
        y = ap.obs["is_psc"].values.astype(int) if "is_psc" in ap.obs else np.zeros(ap.n_obs, int)
        site = (
            ap.obs["dataset_id"].values.astype(str)
            if "dataset_id" in ap.obs
            else np.array(["unknown"] * ap.n_obs)
        )
        Xs.append(X)
        ys.append(y)
        sites.append(site)
    return (
        np.vstack(Xs),
        np.concatenate(ys),
        np.concatenate(sites),
    )


def run_multisite_cv(
    adatas,
    config: Config | None = None,
) -> Dict[str, Any]:
    """Leave-one-site-out CV across the simulated publications."""
    config = config or Config()
    X, y, sites = _prep(adatas)
    fold_ids = sorted(set(sites))
    per_fold: List[Dict[str, Any]] = []
    for k, held in enumerate(fold_ids):
        tr = sites != held
        te = sites == held
        if tr.sum() == 0 or te.sum() == 0:
            continue
        model = ResipscEnsemble(config)
        model.fit(X[tr], y[tr])
        p = model.predict_proba(X[te])[:, 1]
        m = _metrics(y[te], p)
        m.update({"fold": k + 1, "held_out_site": str(held),
                  "n_test": int(te.sum()), "n_test_psc": int(y[te].sum())})
        per_fold.append(m)
        LOGGER.info("LOPO fold %d (%s): ROC-AUC %.3f", k + 1, held, m["roc_auc"])
    return {
        "scheme": "leave-one-site-out (LOPO) 4-fold CV across publications",
        "per_fold": per_fold,
        "n_folds": len(per_fold),
    }


def run_lineage_cv(
    adatas,
    config: Config | None = None,
) -> Dict[str, Any]:
    """Cross-lineage generalisation: train on 2 germ layers, test on the 3rd."""
    config = config or Config()
    results: List[Dict[str, Any]] = []
    lineages = ["ectoderm", "mesoderm", "endoderm"]
    by_lineage = {}
    for a in adatas:
        lin = a.obs["lineage"].iloc[0] if "lineage" in a.obs else "unknown"
        by_lineage.setdefault(str(lin), []).append(a)
    for held in lineages:
        train_set = [a for lin, lst in by_lineage.items() if lin != held for a in lst]
        test_set = by_lineage.get(held, [])
        if not train_set or not test_set:
            continue
        Xtr, ytr, _ = _prep(train_set)
        Xte, yte, _ = _prep(test_set)
        # align feature widths by trimming to the min
        w = min(Xtr.shape[1], Xte.shape[1])
        model = ResipscEnsemble(config)
        model.fit(Xtr[:, :w], ytr)
        p = model.predict_proba(Xte[:, :w])[:, 1]
        m = _metrics(yte, p)
        m.update({"held_out_lineage": held, "n_test": int(len(yte))})
        results.append(m)
        LOGGER.info("lineage CV (%s): ROC-AUC %.3f", held, m["roc_auc"])
    return {"scheme": "cross-lineage transfer (train 2 layers, test held-out)", "per_lineage": results}
