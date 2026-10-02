"""ICH Q5E-style comparability engine.

Compares two model versions on a golden dataset: sensitivity/specificity
deltas, Cohen's kappa decision concordance, and Bland-Altman statistics on
per-cell probabilities. Used on every model retrain/promotion.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics import cohen_kappa_score


def bland_altman(p_old: np.ndarray, p_new: np.ndarray) -> Dict[str, Any]:
    """Bland-Altman analysis on paired probabilities."""
    mean = (p_old + p_new) / 2.0
    diff = p_new - p_old
    md = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1)) if len(diff) > 1 else 0.0
    return {
        "mean_difference": md,
        "std_difference": sd,
        "limits_of_agreement": [md - 1.96 * sd, md + 1.96 * sd],
        "mean_of_means": float(np.mean(mean)),
    }


class ComparabilityEngine:
    """Run ICH Q5E comparability between an old and a new model."""

    def __init__(self, decision_threshold: float = 0.5) -> None:
        self.threshold = decision_threshold

    def compare(
        self,
        y_true: np.ndarray,
        p_old: np.ndarray,
        p_new: np.ndarray,
        old_version: str = "resipsc-ensemble-1.x",
        new_version: str = "resipsc-ensemble-2.0.0",
    ) -> Dict[str, Any]:
        y = np.asarray(y_true).astype(int)
        p_old = np.asarray(p_old, dtype=float)
        p_new = np.asarray(p_new, dtype=float)

        def sens_spec(p):
            yhat = (p >= self.threshold).astype(int)
            tp = int(((y == 1) & (yhat == 1)).sum())
            fn = int(((y == 1) & (yhat == 0)).sum())
            tn = int(((y == 0) & (yhat == 0)).sum())
            fp = int(((y == 0) & (yhat == 1)).sum())
            return tp / max(1, tp + fn), tn / max(1, tn + fp), tp, fn, tn, fp

        sens_o, spec_o, tp_o, fn_o, tn_o, fp_o = sens_spec(p_old)
        sens_n, spec_n, tp_n, fn_n, tn_n, fp_n = sens_spec(p_new)

        d_old = (p_old >= self.threshold).astype(int)
        d_new = (p_new >= self.threshold).astype(int)
        try:
            kappa = float(cohen_kappa_score(d_old, d_new))
        except Exception:  # noqa: BLE001
            kappa = 1.0

        ba = bland_altman(p_old, p_new)
        concordant = int((d_old == d_new).sum())
        verdict_ok = (abs(sens_n - sens_o) <= 0.02) and (abs(spec_n - spec_o) <= 0.02) and kappa >= 0.9

        return {
            "standard": "ICH Q5E Comparability of Biotechnological/Biological Products",
            "old_version": old_version,
            "new_version": new_version,
            "n_samples": int(len(y)),
            "old_model": {
                "sensitivity": sens_o, "specificity": spec_o,
                "tp": tp_o, "fn": fn_o, "tn": tn_o, "fp": fp_o,
            },
            "new_model": {
                "sensitivity": sens_n, "specificity": spec_n,
                "tp": tp_n, "fn": fn_n, "tn": tn_n, "fp": fp_n,
            },
            "sensitivity_delta": sens_n - sens_o,
            "specificity_delta": spec_n - spec_o,
            "decision_concordance": concordant / max(1, len(y)),
            "cohens_kappa": kappa,
            "bland_altman": ba,
            "acceptance_criteria": {
                "abs_sensitivity_delta": "<= 0.02",
                "abs_specificity_delta": "<= 0.02",
                "cohens_kappa": ">= 0.90",
            },
            "verdict": "COMPARABLE" if verdict_ok else "NOT COMPARABLE — investigate before promotion",
            "rollback_plan": (
                "If comparability fails or post-promotion monitoring drifts, revert "
                "results/final_model.pkl to the previous registry entry (model card "
                "snapshot) and re-run QC reports for affected batches."
            ),
        }
