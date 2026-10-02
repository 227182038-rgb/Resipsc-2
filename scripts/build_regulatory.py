#!/usr/bin/env python3
"""build_regulatory.py — FDA/EMA/ICH regulatory package PDF (resipsc v2.0)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from resipsc.compliance.fmea import build_fmea_worksheet

TEAL = colors.HexColor("#0f766e")
DARK = colors.HexColor("#1f2937")
SLATE = colors.HexColor("#475569")
LIGHT = colors.HexColor("#f1f5f9")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, textColor=TEAL, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, textColor=DARK, spaceAfter=4, spaceBefore=6)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontSize=8.6, leading=11.5, textColor=SLATE)
SMALL = ParagraphStyle("SMALL", parent=styles["BodyText"], fontSize=7.2, leading=9.2, textColor=SLATE)
TITLE = ParagraphStyle("TITLE", parent=styles["Title"], fontSize=19, textColor=TEAL, alignment=TA_CENTER)
SUB = ParagraphStyle("SUB", parent=styles["BodyText"], fontSize=9, alignment=TA_CENTER, textColor=SLATE)


def _tbl(data, widths=None, size=7.2, header=True):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [
        ("FONTSIZE", (0, 0), (-1, -1), size),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(st))
    return t


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default if default is not None else {}


def build(out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc = SimpleDocTemplate(
        out_path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="resipsc Regulatory Package", author="resipsc v2.0.0",
    )
    story = []
    ms = _load("results/multisite_results.json")
    sp = _load("results/spikein_results.json")
    card = _load("results/model_card.json")

    # cover
    story.append(Spacer(1, 30 * mm))
    story.append(Paragraph("resipsc v2.0.0", TITLE))
    story.append(Paragraph("Regulatory Package — Residual PSC Detection Software", SUB))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("FDA · EMA · ICH · GAMP 5 · 21 CFR Part 11 · GMLP · PCCP", SUB))
    story.append(Spacer(1, 10 * mm))
    story.append(_tbl([
        ["Document", "resipsc Regulatory Package (RUO)"],
        ["Software version", "2.0.0 (resipsc-ensemble-2.0.0)"],
        ["Model card", (card.get("config_hash") or "n/a")],
        ["Intended use", "Computational residual PSC detection in scRNA-seq of PSC-derived cell therapy products"],
        ["Regulatory status", "Research Use Only — NOT FDA-cleared"],
        ["Audit trail", "db/audit.db (SHA-256 hash-chained, append-only)"],
    ], widths=[45 * mm, 130 * mm], header=False, size=8))
    story.append(PageBreak())

    # 1 FDA
    story.append(Paragraph("1. FDA Position and Applicable Regulations", H1))
    story.append(Paragraph("1.1 21 CFR 1271 — Human Cells, Tissues, and Cellular and Tissue-Based Products (HCT/Ps)", H2))
    story.append(Paragraph(
        "PSC-derived cell therapy products that are more than minimally manipulated fall under 21 CFR 1271 "
        "and 21 CFR 211 (cGMP). Release testing for residual undifferentiated PSCs is required before "
        "administration because transplanted residual PSCs can form teratomas. resipsc computes a "
        "per-batch residual PSC fraction and emits a disposition recommendation aligned with these rules: "
        "RELEASE at an observed fraction at or below 0.001% (with orthogonal confirmation), HOLD between "
        "0.001% and 1% pending QA review, and QUARANTINE above 1%. The tool documents the biological "
        "rationale (pluripotency programme detection via OCT4/POU5F1, NANOG, SOX2 and an extended "
        "8-marker panel) and maps detected cells to germ-layer lineages and 22 teratoma-relevant "
        "anatomical sites with literature-derived priors.", BODY))
    story.append(Paragraph("1.2 21 CFR Part 11 — Electronic Records and Electronic Signatures", H2))
    story.append(Paragraph(
        "The audit trail is implemented as an append-only SQLite event log in which every event carries a "
        "SHA-256 hash computed over the previous event's hash, the event payload and a UTC timestamp, "
        "forming a tamper-evident chain. No UPDATE or DELETE code path exists for audit rows; the chain "
        "can be verified programmatically via the /api/audit endpoint, and exports to CSV are provided "
        "for inspectors. The log captures user ID, timestamp, action, entity, old and new values, reason "
        "for change, and IP address. Records are retained for at least 5 years after batch release "
        "(10 years recommended for cell therapies). Electronic signature blocks are present on QC "
        "reports for QA/QP wet-ink or 21 CFR Part 11-compliant e-signature workflows.", BODY))
    story.append(Paragraph("1.3 Good Machine Learning Practice (GMLP)", H2))
    story.append(_tbl([
        ["#", "GMLP principle (FDA/Health Canada/MHRA, Oct 2021)", "resipsc implementation"],
        ["1", "Multidisciplinary expertise", "ML, QA, bioinformatics and regulatory roles defined in FMEA team and RBAC"],
        ["2", "Good software engineering and security practices", "Typed codebase, pinned dependencies (SBOM), Docker build, RBAC, session timeout"],
        ["3", "Data management reflecting intended use", "Training corpus registry with provenance; data hash in model card"],
        ["4", "Data quality and relevance", "Cell/gene QC filters, biomarker cross-check, batch-effect flags"],
        ["5", "Model development and separation of datasets", "4-fold multi-site CV, cross-lineage CV, held-out spike-in validation"],
        ["6", "Independence of training and test data", "Leave-site-group-out folds; frozen golden dataset for Q5E comparability"],
        ["7", "Human-AI interface transparency", "Probability distribution, per-cell table, QC flags, threshold sensitivity"],
        ["8", "Testing for intended use", "Spike-in sweeps, ablation, multi-seed reproducibility, calibration metrics"],
        ["9", "Deployed model monitoring", "CalibrationMonitor (KL/JS/Wasserstein/KS) with SQLite persistence"],
        ["10", "Periodic model review and retraining", "PCCP with defined retraining triggers and rollback plan"],
    ], widths=[7 * mm, 70 * mm, 95 * mm], size=6.8))
    story.append(Paragraph("1.4 PCCP — Predetermined Change Control Plan (FDA, Dec 2024)", H2))
    story.append(Paragraph(
        "A PCCP template is maintained (paper/pccp_template.md) describing planned modifications "
        "(weights, feature space, thresholds, site priors), the modification protocol (data requirements, "
        "retraining procedure, acceptance criteria, verification) and the impact assessment "
        "(benefit-risk, post-market monitoring, rollback). A PCCP-delta is emitted on every model retrain "
        "and every promotion is recorded in the audit trail with a reference to the delta document.", BODY))
    story.append(PageBreak())

    # 2 EMA
    story.append(Paragraph("2. EMA Position", H1))
    story.append(Paragraph("2.1 EMEA/CHMP/410869/2006 — Guideline on Human Cell-Based Medicinal Products", H2))
    story.append(Paragraph(
        "The guideline requires identity, potency, purity, microbiological safety, viability and "
        "tumorigenicity testing for cell-based medicinal products. For purity, residual undifferentiated "
        "cells must be below a sponsor-justified threshold, with the analytical choice justified. "
        "resipsc supports this justification by providing a quantitative, probability-calibrated residual "
        "PSC fraction with bootstrap 95% confidence intervals and an orthogonal biomarker cross-check "
        "(OCT4/NANOG/SOX2 panel agreement is reported on every run). A Qualified Person release decision "
        "remains defensible when the fraction is at or below 0.001% with orthogonal confirmation; "
        "resipsc's HOLD disposition maps to the QP consultation path, and QUARANTINE to a failed "
        "purity criterion requiring investigation.", BODY))
    story.append(Paragraph("2.2 European QP interaction", H2))
    story.append(Paragraph(
        "Every QC report includes the regulatory context section with the EMA rationale, the observed "
        "fraction with CI, and recommended orthogonal assays (ddPCR for LIN28A/ESRG, immunostaining for "
        "OCT4/TRA-1-60, or histological embryoid-body assay). The signature block reserves an explicit "
        "QP approval line, and the audit trail captures who reviewed what and when.", BODY))
    story.append(PageBreak())

    # 3 ICH
    story.append(Paragraph("3. ICH Guidelines", H1))
    story.append(Paragraph("3.1 ICH Q5E — Comparability of Biotechnological/Biological Products", H2))
    story.append(Paragraph(
        "Every model promotion requires a comparability study between the previous and new model on the "
        "golden dataset: sensitivity delta, specificity delta, decision concordance and Cohen's kappa "
        "with acceptance criteria (|Δsens| ≤ 0.02, |Δspec| ≤ 0.02, κ ≥ 0.90), plus a Bland-Altman "
        "analysis of paired per-cell probabilities. The comparability engine and report generator are "
        "implemented in the resipsc package and exposed at POST /api/comparability. Results are "
        "persisted to results/comparability_report.json and the audit trail records the promotion.", BODY))
    story.append(Paragraph("3.2 ICH Q9(R1) — Quality Risk Management", H2))
    fmea = build_fmea_worksheet()
    rows = [["ID", "Component", "Failure mode", "S", "O", "D", "RPN", "Class"]] + [
        [r["id"], r["component"], r["failure_mode"][:64], str(r["severity"]),
         str(r["occurrence"]), str(r["detection"]), str(r["rpn"]), r["risk_class"]]
        for r in fmea["rows"][:12]
    ]
    story.append(Paragraph(
        "A formal FMEA covers input data quality, model failure modes, infrastructure and governance. "
        "Risk priority numbers (RPN = severity × occurrence × detection) drive the control strategy. "
        "Highest-ranked items: " + "; ".join(
            f"{r['id']} {r['failure_mode'][:40]} (RPN {r['rpn']})" for r in fmea["rows"][:3]
        ) + ".", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(_tbl(rows, widths=[13 * mm, 24 * mm, 62 * mm, 8 * mm, 8 * mm, 8 * mm, 13 * mm, 15 * mm], size=6.6))
    story.append(Paragraph("3.3 ICH Q10 — Pharmaceutical Quality System", H2))
    story.append(Paragraph(
        "Change management: PCCP-delta documents and CAPA workflow for drift; Management review: PQS "
        "metrics surfaced on the dashboard (calibration status, batch dispositions); Continual "
        "improvement: post-market surveillance through per-batch drift monitoring; Knowledge "
        "management: model card, validation data, decision rationale and audit trail retained in the "
        "repository structure.", BODY))
    story.append(PageBreak())

    # 4 GAMP 5
    story.append(Paragraph("4. GAMP 5 Second Edition — Category 5 Custom Software", H1))
    story.append(_tbl([
        ["Phase", "Scope", "resipsc deliverable"],
        ["IQ — Installation Qualification", "Version manifests, environment configuration captured in immutable build artifacts",
         "Dockerfile with pinned dependencies + sbom.json; deterministic build; model card with config hash"],
        ["OQ — Operational Qualification", "Functional tests under stressed conditions: input range, boundary tests, fault injection, security",
         "Universal QC on any file type/size with memory guards; chunked-upload race-condition-free (sequential); server crash protection (instrumentation.ts); RBAC-ready API"],
        ["PQ — Performance Qualification", "End-to-end runs on representative samples against acceptance criteria",
         "Spike-in sweeps with quantification calibration; acceptance criteria: sensitivity ≥ 99% and specificity ≥ 95% at the qualified operating point, turnaround ≤ 1 hr (current build: seconds per batch)"],
    ], widths=[38 * mm, 62 * mm, 75 * mm], size=7))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Note: the current demonstration build is trained on a hybrid corpus (simulated multi-site data "
        "plus a real PBMC negative reference). PQ acceptance criteria are defined for the qualified "
        "system on clinical manufacturing data, which requires the wet-lab validation programme "
        "described in paper/wet_lab_limitation.md.", BODY))

    # 5 benchmarks summary
    story.append(Paragraph("5. Current Build Performance Summary", H1))
    sm = ms.get("summary", [])
    story.append(_tbl(
        [["Model", "ROC-AUC (multi-site CV)", "Sensitivity", "Specificity"]] +
        [[r.get("model", "?"), f"{r.get('roc_auc_mean', '?')} ± {r.get('roc_auc_std', '?')}",
          str(r.get("sensitivity_mean", "?")), str(r.get("specificity_mean", "?"))] for r in sm],
        widths=[45 * mm, 50 * mm, 40 * mm, 40 * mm], size=7.6))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Spike-in validation: limit of detection {100 * (sp.get('limit_of_detection_fraction') or 0):.4f}% "
        f"with quantification calibration (sens {sp.get('quantification_calibration', {}).get('sens')}, "
        f"fpr {sp.get('quantification_calibration', {}).get('fpr')}). "
        "Wet-lab reference LODs: HEC 0.001%, ddPCR (Kuroda) 0.01%, lncRNA flow 0.0001%, in vivo teratoma 0.1-1%.", BODY))

    # 6 cybersecurity
    story.append(Paragraph("6. Cybersecurity and Data Privacy", H1))
    story.append(Paragraph(
        "scRNA-seq profiles are treated as PHI under the HIPAA Security Rule (identifiable even after "
        "de-identification). Administrative safeguards: RBAC roles (admin, QC officer, QA, viewer) and "
        "training; physical: cloud infrastructure controls inherited from the hosting environment; "
        "technical: authentication on all mutating API endpoints, 15-minute session timeout, audit trail "
        "on every state change, and hash-chained record integrity. Target certifications: HIPAA + "
        "SOC 2 Type II (Year 1), ISO 27001 (Year 2), HITRUST r2 (Year 3).", BODY))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "This package describes a Research Use Only demonstration build. It is not a regulatory "
        "submission and the software is not FDA-cleared or CE-marked.", SUB))

    doc.build(story)
    return out_path


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "download/resipsc_regulatory_package.pdf"
    path = build(out)
    print(json.dumps({"status": "ok", "pdf": path, "size_kb": round(os.path.getsize(path) / 1024, 1)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
