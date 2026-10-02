"""Configuration for the resipsc pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class Config:
    """Training / inference configuration.

    Two presets matter (PART 7 of the spec):

    * low-RAM (< 8 GB):   n_hvg=300, max_cells_per_dataset=800, ae_epochs=10,
                           xgb/rf estimators 80, skip_transformer=True
    * full-RAM (>= 8 GB): n_hvg=500, max_cells_per_dataset=2000, ae_epochs=15,
                           xgb/rf estimators 100

    Decision thresholds follow FDA 21 CFR 1271 guidance used by the QC report:
    release <= 0.001% residual PSC, quarantine > 1%.
    """

    # --- feature engineering -------------------------------------------------
    n_hvg: int = 300
    max_cells_per_dataset: int = 800
    random_state: int = 42

    # --- model hyperparameters -------------------------------------------------
    xgb_n_estimators: int = 80
    xgb_max_depth: int = 4
    xgb_learning_rate: float = 0.1
    rf_n_estimators: int = 80
    svm_kernel: str = "linear"
    mlp_hidden: tuple = (64, 32)
    mlp_epochs: int = 60
    ae_epochs: int = 10
    ae_latent: int = 32
    transformer_epochs: int = 2
    transformer_dim: int = 32
    skip_transformer: bool = True

    # --- ensemble -------------------------------------------------------------
    classical_weight: float = 0.6
    deep_weight: float = 0.4
    # intra-classical weights: XGBoost + RandomForest + SVM
    xgb_weight: float = 0.5
    rf_weight: float = 0.25
    svm_weight: float = 0.25

    # --- decision thresholds (FDA-aligned) --------------------------------------
    decision_threshold: float = 0.5
    release_max_pct: float = 0.001   # percent of total cells
    hold_min_pct: float = 1.0         # percent of total cells

    # --- spike-in evaluation ----------------------------------------------------
    spikein_ratios: tuple = (0.001, 0.01, 0.1)  # PSC cell fractions
    spikein_replicates: int = 2

    # --- misc -------------------------------------------------------------------
    n_jobs: int = max(1, (os.cpu_count() or 2) - 1)
    results_dir: str = "results"
    db_dir: str = "db"
    seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # tuples -> lists for JSON serialisation
        for k, v in list(d.items()):
            if isinstance(v, tuple):
                d[k] = list(v)
        return d


def default_config() -> Config:
    """Return a Config sized for the current machine.

    Machines with < 8 GB RAM get the aggressive-subsampling profile from
    PART 7 of the specification; larger machines get the fuller profile.
    """
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            mem_kb = int(fh.readline().split()[1])
        total_gb = mem_kb / (1024 * 1024)
    except Exception:  # noqa: BLE001 - non-Linux / unexpected format
        total_gb = 8.0

    if total_gb < 8.0:
        return Config(
            n_hvg=300,
            max_cells_per_dataset=800,
            ae_epochs=10,
            transformer_epochs=2,
            xgb_n_estimators=80,
            rf_n_estimators=80,
            svm_kernel="linear",
            skip_transformer=True,
            spikein_replicates=2,
        )
    return Config(
        n_hvg=300,
        max_cells_per_dataset=2000,
        ae_epochs=15,
        transformer_epochs=3,
        xgb_n_estimators=100,
        rf_n_estimators=100,
        svm_kernel="linear",
        skip_transformer=True,
        spikein_replicates=3,
    )
