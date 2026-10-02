"""PCCP template generator (FDA Dec 2024 guidance).

The Predetermined Change Control Plan documents: (1) the planned model
modifications, (2) the modification protocol (validation methodology), and
(3) the impact assessment framework. A PCCP-delta is emitted on every model
retrain via this template.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_pccp_template(
    model_version: str = "resipsc-ensemble-2.0.0",
    retrain_trigger: str = "Calibration drift (KL > 0.10 or KS > 0.15) on two consecutive batches, or annual review",
    changes: Optional[list] = None,
) -> Dict[str, Any]:
    """Return the PCCP structure (markdown-renderable)."""
    changes = changes or [
        {
            "change_id": "PC-01",
            "component": "Model weights",
            "planned_modification": "Periodic retraining on the accumulated QC corpus (new synthetic + real batches)",
            "frequency": "Annual or drift-triggered",
            "risk": "Performance regression on previously released product types",
        },
        {
            "change_id": "PC-02",
            "component": "Feature space",
            "planned_modification": "Expansion of the highly-variable gene set (300 -> 500) with re-validated benchmarks",
            "frequency": "Rare, versioned",
            "risk": "Distribution shift in score calibration",
        },
        {
            "change_id": "PC-03",
            "component": "Decision thresholds",
            "planned_modification": "Recalibration of the 0.5 decision threshold against new spike-in data",
            "frequency": "With each retrain",
            "risk": "Altered release/quarantine boundaries",
        },
        {
            "change_id": "PC-04",
            "component": "Site prior table",
            "planned_modification": "Update teratoma site priors when new epidemiological literature is published",
            "frequency": "Rare, literature-driven",
            "risk": "Changed clinical notification content",
        },
    ]
    return {
        "title": "Predetermined Change Control Plan (PCCP) — resipsc",
        "model": model_version,
        "guidance": (
            "FDA guidance: Marketing Submission Recommendations for a Predetermined "
            "Change Control Plan for AI-Enabled Device Software Functions (Dec 2024)"
        ),
        "section_1_description_of_changes": {
            "planned_changes": changes,
            "out_of_scope": [
                "Changes to intended use or indications",
                "Changes to the clinical claim (residual PSC detection)",
                "Architecture swaps that alter the intended-use statement",
            ],
        },
        "section_2_modification_protocol": {
            "data_requirements": (
                "Retraining corpus must include all production QC batches since the "
                "last promotion, plus the frozen golden dataset (>= 100 representative "
                "samples spanning lineages and spike-in ratios)."
            ),
            "retraining_procedure": [
                "1. Freeze current model snapshot + model card hash (rollback anchor)",
                "2. Retrain on expanded corpus with fixed random seeds",
                "3. Re-run multi-site CV, cross-lineage CV and spike-in sweep",
                "4. Run ICH Q5E comparability vs current model on the golden dataset",
                "5. Emit PCCP-delta document and updated model card",
                "6. QA approval gate; audit-logged promotion; update registry",
            ],
            "acceptance_criteria": {
                "roc_auc": ">= 0.90 on multi-site CV (mean over folds)",
                "sensitivity_delta": "<= 0.02 vs current model (golden dataset)",
                "specificity_delta": "<= 0.02 vs current model (golden dataset)",
                "cohens_kappa": ">= 0.90 decision concordance vs current model",
                "spikein_lod": "<= 0.01% at recall >= 0.9",
                "calibration": "Brier < 0.15 and ECE < 0.15 vs biomarker reference",
            },
            "verification": (
                "Automated checks in CI (bootstrap CIs, multi-seed stability across "
                "seeds 42/123/456/789/1024, ablation parity); manual QA review of the "
                "PCCP-delta document."
            ),
        },
        "section_3_impact_assessment": {
            "benefit_risk": (
                "Change management preserves the safety benefit of early residual-PSC "
                "detection while controlling regression risk via comparability gates."
            ),
            "post_market_monitoring": (
                "CalibrationMonitor drift metrics (KL/JS/Wasserstein/KS) tracked per "
                "batch; CAPA workflow for two consecutive DRIFTED statuses."
            ),
            "rollback_plan": (
                "Restore previous model snapshot from the registry, re-run Q5E "
                "comparability, and document in the audit trail within 1 business day."
            ),
        },
        "retrain_trigger": retrain_trigger,
        "records": "All promotions are recorded in db/audit.db with PCCP-delta references.",
    }
