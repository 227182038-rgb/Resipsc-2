"""Auto-generate the ICH Q5E comparability report (JSON + markdown)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict


def build_comparability_report(
    comparison: Dict[str, Any], out_dir: str = "results"
) -> Dict[str, Any]:
    """Wrap a ComparabilityEngine result and persist results/comparability_report.json."""
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC"
    report = {
        "title": "ICH Q5E Comparability Report — model promotion",
        "generated_at_utc": now,
        "standard": comparison.get("standard", "ICH Q5E"),
        "old_version": comparison.get("old_version"),
        "new_version": comparison.get("new_version"),
        "n_samples": comparison.get("n_samples"),
        "metrics": {
            "old": comparison.get("old_model"),
            "new": comparison.get("new_model"),
            "sensitivity_delta": comparison.get("sensitivity_delta"),
            "specificity_delta": comparison.get("specificity_delta"),
            "decision_concordance": comparison.get("decision_concordance"),
            "cohens_kappa": comparison.get("cohens_kappa"),
            "bland_altman": comparison.get("bland_altman"),
        },
        "acceptance_criteria": comparison.get(
            "acceptance_criteria",
            {
                "abs_sensitivity_delta": "<= 0.02",
                "abs_specificity_delta": "<= 0.02",
                "cohens_kappa": ">= 0.90",
            },
        ),
        "verdict": comparison.get("verdict"),
        "rollback_plan": comparison.get("rollback_plan"),
        "signatures": {
            "ml_lead": "pending e-signature (21 CFR Part 11)",
            "qa_officer": "pending e-signature (21 CFR Part 11)",
        },
    }
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    with open(Path(out_dir) / "comparability_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    return report
