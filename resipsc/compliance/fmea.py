"""FMEA worksheet builder (ICH Q9(R1) risk management).

Formal Failure Mode and Effects Analysis for the ML system: input data
quality, model failure modes, infrastructure failures and drift. Risk
priority numbers (RPN = severity x occurrence x detection) are computed and
rows are sorted by RPN.
"""

from __future__ import annotations

from typing import Any, Dict, List

FMEA_ROWS: List[Dict[str, Any]] = [
    {
        "id": "FM-01", "component": "Input data", "failure_mode": "Low cell count (< 200 cells sequenced)",
        "effect": "Residual PSC fraction estimate has a wide CI; false RELEASE possible",
        "severity": 9, "occurrence": 4, "detection": 5,
        "controls": "Critical QC flag on reports; recommend minimum 500 cells",
        "mitigation": "Sampling SOP; automated n<200 critical flag blocks auto-RELEASE",
    },
    {
        "id": "FM-02", "component": "Input data", "failure_mode": "Batch effects between product runs",
        "effect": "False-positive PSC calls inflate the estimated fraction",
        "severity": 8, "occurrence": 6, "detection": 4,
        "controls": "Biomarker cross-check warning; Harmony re-scoring pathway",
        "mitigation": "Batch-effect QC flag; cross-check agreement printed on every report",
    },
    {
        "id": "FM-03", "component": "Input data", "failure_mode": "Ambient RNA contamination carries marker signal",
        "effect": "Non-PSC cells score positive on OCT4/NANOG/SOX2",
        "severity": 6, "occurrence": 5, "detection": 6,
        "controls": "SoupX-style decontamination upstream recommended",
        "mitigation": "Model-only vs biomarker-only discrepancy counts surfaced in report",
    },
    {
        "id": "FM-04", "component": "Input data", "failure_mode": "Doublets simulate PSC gene programmes",
        "effect": "Doublet cells classified as PSC -> fraction overestimate",
        "severity": 5, "occurrence": 5, "detection": 5,
        "controls": "Scrublet/DoubletFinder upstream; doublet-aware training data",
        "mitigation": "Synthetic doublets included in training corpus",
    },
    {
        "id": "FM-05", "component": "Model", "failure_mode": "False-negative: tumorigenic lot released",
        "effect": "Patient safety impact — teratoma formation post-transplant",
        "severity": 10, "occurrence": 2, "detection": 7,
        "controls": "Conservative decision threshold; spike-in LOD monitoring; binomial test on every report",
        "mitigation": "Hold/Quarantine dispositions above 0.001%; orthogonal confirmation required for release",
    },
    {
        "id": "FM-06", "component": "Model", "failure_mode": "False-positive: conforming lot rejected",
        "effect": "Costly batch loss and manufacturing delay",
        "severity": 4, "occurrence": 5, "detection": 3,
        "controls": "Biomarker cross-check; threshold sensitivity table",
        "mitigation": "QA review pathway (HOLD) rather than auto-reject",
    },
    {
        "id": "FM-07", "component": "Model", "failure_mode": "Silent drift of score distribution",
        "effect": "Gradual degradation of detection performance",
        "severity": 7, "occurrence": 4, "detection": 3,
        "controls": "CalibrationMonitor (KL/JS/Wasserstein/KS) per batch with SQLite persistence",
        "mitigation": "Drift triggers retraining per PCCP; CAPA workflow",
    },
    {
        "id": "FM-08", "component": "Model", "failure_mode": "Out-of-lineage product (unseen germ layer)",
        "effect": "Reduced sensitivity on products outside training distribution",
        "severity": 7, "occurrence": 3, "detection": 5,
        "controls": "Cross-lineage CV metrics published on dashboard",
        "mitigation": "Model credentials show lineage AUCs; retrain with new lineages",
    },
    {
        "id": "FM-09", "component": "Infrastructure", "failure_mode": "Partial file upload / corrupted h5ad",
        "effect": "QC run fails or analyses truncated data",
        "severity": 6, "occurrence": 3, "detection": 4,
        "controls": "Chunked upload with assembly validation; size checks",
        "mitigation": "Graceful JSON parse errors; server crash protection (instrumentation.ts)",
    },
    {
        "id": "FM-10", "component": "Infrastructure", "failure_mode": "Audit trail unavailable (DB lock)",
        "effect": "Part 11 non-compliance for affected events",
        "severity": 8, "occurrence": 2, "detection": 2,
        "controls": "WAL mode; 30s busy timeout; chain verification endpoint",
        "mitigation": "API returns explicit 503 if audit write fails — fail closed",
    },
    {
        "id": "FM-11", "component": "Governance", "failure_mode": "Unauthorised model swap without comparability",
        "effect": "Undocumented performance change in a regulated workflow",
        "severity": 9, "occurrence": 2, "detection": 3,
        "controls": "Model registry + PCCP-delta on retrain; audit-logged promotion",
        "mitigation": "ICH Q5E comparability gate before promotion",
    },
    {
        "id": "FM-12", "component": "Governance", "failure_mode": "Privilege escalation / audit tampering",
        "effect": "Loss of record integrity (21 CFR Part 11)",
        "severity": 10, "occurrence": 1, "detection": 2,
        "controls": "Append-only schema (no UPDATE/DELETE code paths); SHA-256 chain; RBAC",
        "mitigation": "Chain verification API; alert on mismatch",
    },
]


def build_fmea_worksheet() -> Dict[str, Any]:
    """Compute RPNs and return the FMEA worksheet structure."""
    rows = []
    for r in FMEA_ROWS:
        rpn = r["severity"] * r["occurrence"] * r["detection"]
        risk_class = (
            "HIGH" if rpn >= 150 else "MEDIUM" if rpn >= 60 else "LOW"
        )
        rows.append({**r, "rpn": rpn, "risk_class": risk_class})
    rows.sort(key=lambda x: -x["rpn"])
    high = sum(1 for r in rows if r["risk_class"] == "HIGH")
    return {
        "title": "FMEA — residual PSC detection ML system (resipsc v2.0)",
        "standard": "ICH Q9(R1) Quality Risk Management",
        "scale": "RPN = Severity (1-10) x Occurrence (1-10) x Detection (1-10); HIGH >= 150, MEDIUM >= 60, LOW < 60",
        "team": "ML engineering, QA, bioinformatics, regulatory affairs",
        "rows": rows,
        "summary": {
            "n_failure_modes": len(rows),
            "high_risk": high,
            "medium_risk": sum(1 for r in rows if r["risk_class"] == "MEDIUM"),
            "low_risk": sum(1 for r in rows if r["risk_class"] == "LOW"),
            "max_rpn": rows[0]["rpn"] if rows else 0,
        },
        "review_cycle": "Annually and after any High-severity CAPA or model promotion",
        "linked_documents": [
            "paper/pccp_template.md (change control)",
            "paper/wet_lab_limitation.md (validation gaps)",
            "db/audit.db (Part 11 trail)",
        ],
    }
