"""Model card generator — auto-emitted on every training run.

Includes intended use, training data summary, performance metrics,
limitations, ethical considerations, training config hash, and the PCCP
delta link for change control.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict

from resipsc.config import Config
from resipsc.models.ensemble import MODEL_VERSION


def generate_model_card(
    config: Config,
    metrics: Dict[str, Any],
    training_data: Dict[str, Any],
    results_dir: str = "results",
    notes: str = "",
) -> Dict[str, Any]:
    """Build and persist results/model_card.json."""
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC"
    config_hash = hashlib.sha256(
        json.dumps(config.to_dict(), sort_keys=True).encode()
    ).hexdigest()[:16]
    data_hash = hashlib.sha256(
        json.dumps(training_data, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    card: Dict[str, Any] = {
        "model_version": MODEL_VERSION,
        "model_type": "Weighted ML ensemble (XGBoost+RF+SVM 0.6 / AE+MLP 0.4)",
        "generated_at_utc": now,
        "intended_use": (
            "Computational detection of residual pluripotent stem cells in "
            "single-cell RNA-seq of PSC-derived cell therapy products. Research "
            "Use Only — NOT FDA-cleared and not a clinical release test."
        ),
        "out_of_scope_uses": [
            "Clinical diagnosis or patient management",
            "Release testing without orthogonal wet-lab confirmation",
            "Bulk RNA-seq or DNA-based purity assays",
        ],
        "training_data_summary": {
            "corpus": training_data.get("corpus", "hybrid"),
            "datasets": training_data.get("datasets", []),
            "n_cells": training_data.get("n_cells", 0),
            "n_psc": training_data.get("n_psc", 0),
            "data_hash": data_hash,
            "provenance": training_data.get("provenance", ""),
        },
        "performance": {
            k: metrics.get(k)
            for k in (
                "roc_auc", "pr_auc", "sensitivity", "specificity",
                "roc_auc_ci95", "lineage_aucs", "spikein_lod",
            )
            if k in metrics
        },
        "training_config": config.to_dict(),
        "config_hash": config_hash,
        "random_seed": config.random_state,
        "limitations": [
            "Hybrid training corpus: simulated multi-site differentiation data plus a real PBMC reference; clinical manufacturing data not yet included.",
            "Detection ceiling scales with sequenced cell number; below 0.001% the estimate is dominated by sampling noise.",
            "Batch effects can create false positives — the biomarker cross-check must be reviewed before disposition.",
            "Teratoma site priors are literature-derived (Lee 2013; Ben-David 2013; Brederlau 2004; Hentze 2009; Kroon 2008) and not patient data.",
            "No wet-lab orthogonal validation performed (HEC, ddPCR, lncRNA flow outstanding).",
        ],
        "ethical_considerations": (
            "scRNA-seq profiles are potentially identifiable and must be handled "
            "as PHI under the HIPAA Security Rule. The model must not be used as "
            "the sole basis for patient treatment decisions."
        ),
        "regulatory": {
            "gmlp": "Aligned with the 10 GMLP principles (FDA/Health Canada/MHRA, Oct 2021).",
            "pccp": "Predetermined Change Control Plan maintained; PCCP-delta emitted on retrain (FDA Dec 2024 guidance).",
            "ich_q5e": "Comparability study required on every promotion; see comparability_report.json.",
            "part11": "All training and promotion events are recorded in the append-only audit trail (db/audit.db).",
        },
        "maintenance": {
            "retraining_trigger": "Calibration drift (KL > 0.10 or KS > 0.15) on two consecutive batches, or annual review.",
            "rollback_plan": "Restore previous model card + weights snapshot; re-run ICH Q5E comparability; document in CAPA.",
        },
        "notes": notes,
    }
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(results_dir) / "model_card.json", "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2, default=str)
    return card
