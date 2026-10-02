#!/usr/bin/env python3
"""render_qc_pdf.py — 14-page QC report PDF generator.

Usage:
  python scripts/render_qc_pdf.py --report results/qc_reports/<id>.json --out download/report.pdf

Implements the PART 3.4 fix: every string slice uses (value or "")[:N] so a
None value can never raise TypeError.
"""

from __future__ import annotations

import argparse
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

TEAL = colors.HexColor("#0f766e")
DARK = colors.HexColor("#1f2937")
SLATE = colors.HexColor("#475569")
LIGHT = colors.HexColor("#f1f5f9")
ROSE = colors.HexColor("#e11d48")
AMBER = colors.HexColor("#d97706")
EMERALD = colors.HexColor("#059669")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=TEAL, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=DARK, spaceAfter=4)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=SLATE)
SMALL = ParagraphStyle("SMALL", parent=styles["BodyText"], fontSize=7, leading=9, textColor=SLATE)
TITLE = ParagraphStyle("TITLE", parent=styles["Title"], fontSize=20, textColor=TEAL, alignment=TA_CENTER)
SUB = ParagraphStyle("SUB", parent=styles["BodyText"], fontSize=9, alignment=TA_CENTER, textColor=SLATE)


def s(qr, key, default=""):
    """PART 3.4 fix: (qr.get(...) or "")[:80] — None-safe string extraction."""
    v = qr.get(key, default)
    return (v or default) if not isinstance(v, str) else v


def _tbl(data, widths=None, header=True, size=7):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), size),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    t.setStyle(TableStyle(style))
    return t


def fmt(v, nd=4):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def build_pdf(qr: dict, out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title="resipsc QC Report", author="resipsc v2.0.0",
    )
    story = []
    rm = qr.get("report_metadata", {})
    es = qr.get("executive_summary", {})
    rt = qr.get("risk_tier", {})

    # ---------------- Page 1: cover ----------------
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph("resipsc v2.0.0", TITLE))
    story.append(Paragraph("Residual Pluripotent Stem Cell Detection — QC Report", SUB))
    story.append(Spacer(1, 8 * mm))
    decision = s(qr, "decision", "UNKNOWN")
    color = {"RELEASE": EMERALD, "HOLD": AMBER, "QUARANTINE": ROSE}.get(decision, SLATE)
    dec_tbl = Table(
        [[Paragraph(f"<font size=18 color=white><b>{decision}</b></font>",
                    ParagraphStyle("d", parent=BODY, alignment=TA_CENTER))]],
        colWidths=[100 * mm],
    )
    dec_tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color),
                                 ("TOPPADDING", (0, 0), (-1, -1), 8),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.append(dec_tbl)
    story.append(Spacer(1, 8 * mm))
    story.append(_tbl([
        ["Report ID", fmt(rm.get("report_id"))],
        ["Generated (UTC)", fmt(rm.get("generated_at_utc"))],
        ["Batch ID", fmt(rm.get("batch_id"))],
        ["Software", f"resipsc {fmt(rm.get('software_version'))} / report v{fmt(rm.get('report_version'))}"],
        ["Input file", fmt(qr.get("input_file"))],
        ["Input format", fmt(rm.get("input_file_format"))],
        ["Input cells / genes", f"{fmt(rm.get('input_cells'))} / {fmt(rm.get('input_genes'))}"],
        ["Input hash (short)", fmt(rm.get("input_hash_short"))],
        ["Risk tier", f"{fmt(rt.get('tier'))} — {fmt(rt.get('label'))}"],
        ["Intended use", fmt(rm.get("intended_use"))],
    ], widths=[45 * mm, 125 * mm], header=False, size=8))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Research Use Only — NOT FDA-cleared. Computational inference from scRNA-seq; "
        "does not substitute for clinical release testing.", SUB))

    # ---------------- Page 2: executive summary ----------------
    story.append(PageBreak())
    story.append(Paragraph("1. Executive Summary", H1))
    story.append(Paragraph(f"<b>Headline:</b> {fmt(es.get('headline'))}", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Detail:</b> {fmt(es.get('detail'))}", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Caveat:</b> {fmt(es.get('caveat'))}", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>One-line verdict:</b> {fmt(es.get('one_line_verdict'))}", BODY))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("1.1 Decision rationale", H2))
    story.append(Paragraph(fmt(qr.get("decision_reason")), BODY))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("1.2 Risk tier", H2))
    story.append(_tbl([
        ["Tier", "Label", "Threshold band", "FDA rationale"],
        [fmt(rt.get("tier")), fmt(rt.get("label")), fmt(rt.get("numerical_threshold")),
         fmt(rt.get("fda_rationale"))[:300]],
    ], widths=[15 * mm, 45 * mm, 30 * mm, 80 * mm]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>EMA rationale:</b> {fmt(rt.get('ema_rationale'))[:400]}", BODY))

    # ---------------- Page 3: key metrics ----------------
    story.append(PageBreak())
    story.append(Paragraph("2. Key Metrics", H1))
    story.append(_tbl([
        ["Metric", "Value"],
        ["Cells analysed", fmt(qr.get("n_cells"))],
        ["Cells above threshold", fmt(qr.get("n_cells_above_threshold"))],
        ["Estimated PSC fraction", f"{fmt(100 * (qr.get('estimated_psc_fraction') or 0), 4)}%"],
        ["Estimated PSC count", fmt(qr.get("estimated_psc_count"))],
        ["PSC probability mean", fmt(qr.get("psc_probability_mean"))],
        ["PSC probability max", fmt(qr.get("psc_probability_max"))],
        ["Biomarker/model agreement", fmt(qr.get("biomarker_model_agreement"))],
        ["Cross-check warning", fmt(qr.get("cross_check_warning"))[:120]],
        ["Mean teratoma risk score", fmt(qr.get("mean_teratoma_risk_score"))],
        ["Max teratoma risk score", fmt(qr.get("max_teratoma_risk_score"))],
    ], widths=[70 * mm, 100 * mm], size=8))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("2.1 Lineage breakdown", H2))
    lb = qr.get("lineage_breakdown", {}) or {}
    story.append(_tbl([["Lineage", "Cells"]] + [[k, fmt(v)] for k, v in lb.items()],
                      widths=[70 * mm, 100 * mm]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("2.2 Thresholds", H2))
    th = qr.get("thresholds", {}) or {}
    story.append(_tbl([["Parameter", "Value"]] + [[k, fmt(v)] for k, v in th.items()],
                      widths=[70 * mm, 100 * mm]))

    # ---------------- Page 4: statistical confidence ----------------
    story.append(PageBreak())
    story.append(Paragraph("3. Statistical Confidence", H1))
    sc = qr.get("statistical_confidence", {}) or {}
    bc = sc.get("bootstrap_ci_95", {}) or {}
    bt = sc.get("binomial_test", {}) or {}
    ph = sc.get("post_hoc_power", {}) or {}
    story.append(_tbl([
        ["Statistic", "Value"],
        ["Bootstrap 95% CI lower", fmt(bc.get("lower"))],
        ["Bootstrap 95% CI upper", fmt(bc.get("upper"))],
        ["Bootstrap mean / std", f"{fmt(bc.get('mean'))} / {fmt(bc.get('std'))}"],
        ["Bootstrap iterations", fmt(bc.get("n_iterations"))],
        ["Binomial null hypothesis", fmt(bt.get("null_hypothesis"))[:160]],
        ["Binomial p-value", fmt(bt.get("p_value"), 6) if isinstance(bt.get("p_value"), float) else fmt(bt.get("p_value"))],
        ["Significant at alpha 0.05", fmt(bt.get("significant_at_alpha_0_05"))],
        ["Observed / expected under null", f"{fmt(bt.get('observed_count'))} / {fmt(bt.get('expected_under_null'))}"],
        ["Post-hoc power", fmt(ph.get("value"))],
        ["Power interpretation", fmt(ph.get("interpretation"))[:200]],
        ["Sample size", fmt(ph.get("sample_size"))],
    ], widths=[70 * mm, 100 * mm], size=8))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("3.1 Probability distribution", H2))
    pd_ = qr.get("probability_distribution", {}) or {}
    story.append(_tbl([["p50", "p95", "p99", "mean", "max"]] +
                      [[fmt(pd_.get(k)) for k in ("p50", "p95", "p99", "mean", "max")]],
                      widths=[34 * mm] * 5))
    bins = pd_.get("bins", []) or []
    if bins:
        story.append(Spacer(1, 3 * mm))
        story.append(_tbl([["Bin", "Count", "Fraction"]] +
                          [[fmt(b.get("label")), fmt(b.get("count")),
                            fmt(b.get("fraction"), 4)] for b in bins[:10]],
                          widths=[50 * mm, 60 * mm, 60 * mm], size=6))

    # ---------------- Page 5: calibration ----------------
    story.append(PageBreak())
    story.append(Paragraph("4. Calibration", H1))
    cm = qr.get("calibration_metrics", {}) or {}
    story.append(_tbl([
        ["Metric", "Value"],
        ["Brier score (vs biomarker)", fmt(cm.get("brier_score_vs_biomarker"))],
        ["Brier interpretation", fmt(cm.get("brier_interpretation"))[:200]],
        ["ECE surrogate (vs biomarker)", fmt(cm.get("ece_surrogate_vs_biomarker"))],
        ["ECE interpretation", fmt(cm.get("ece_interpretation"))[:200]],
        ["Biomarker/model agreement", fmt(cm.get("biomarker_model_agreement"))],
    ], widths=[70 * mm, 100 * mm], size=8))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("4.1 Threshold sensitivity", H2))
    ts = qr.get("threshold_sensitivity", {}) or {}
    tr_ = ts.get("thresholds", {}) or {}
    story.append(_tbl(
        [["Threshold", "Cells above", "Fraction %"]] +
        [[fmt(k), fmt(v.get("n_above")), fmt(v.get("fraction_pct"), 4)]
         for k, v in tr_.items()],
        widths=[50 * mm, 60 * mm, 60 * mm]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Stability:</b> {fmt(ts.get('decision_stability'))}", BODY))

    # ---------------- Page 6: classification + flags ----------------
    story.append(PageBreak())
    story.append(Paragraph("5. Per-cell Classification", H1))
    pc = qr.get("per_cell_classification", {}) or {}
    counts = pc.get("counts", {}) or {}
    fracs = pc.get("fractions", {}) or {}
    interp = pc.get("interpretation", {}) or {}
    story.append(_tbl(
        [["Class", "Count", "Fraction"]] +
        [[fmt(k), fmt(counts.get(k)), fmt(fracs.get(k))] for k in counts],
        widths=[60 * mm, 60 * mm, 50 * mm]))
    story.append(Spacer(1, 4 * mm))
    for k in counts:
        story.append(Paragraph(f"<b>{fmt(k)}:</b> {fmt(interp.get(k))[:260]}", SMALL))
        story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph("5.1 QC flags", H2))
    flags = qr.get("qc_flags", []) or []
    story.append(_tbl(
        [["Severity", "Category", "Message", "Action"]] +
        [[fmt(f.get("severity")), fmt(f.get("category")),
          fmt(f.get("message"))[:140], fmt(f.get("action"))[:140]] for f in flags],
        widths=[20 * mm, 28 * mm, 61 * mm, 61 * mm], size=6.5))

    # ---------------- Page 7: regulatory ----------------
    story.append(PageBreak())
    story.append(Paragraph("6. Regulatory Context", H1))
    rc = qr.get("regulatory_context", {}) or {}
    story.append(Paragraph("<b>FDA</b>", H2))
    story.append(Paragraph(fmt(rc.get("fda"))[:900] or "", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("<b>EMA</b>", H2))
    story.append(Paragraph(fmt(rc.get("ema"))[:900] or "", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("<b>ICH</b>", H2))
    story.append(Paragraph(fmt(rc.get("ich"))[:900] or "", BODY))
    story.append(Spacer(1, 3 * mm))
    story.append(_tbl([["Observed PSC fraction %", "Disposition", "Audit trail"],
                       [fmt(rc.get("observed_psc_fraction_pct")), fmt(rc.get("disposition_code")),
                        fmt(rc.get("audit_trail"))[:120]]],
                      widths=[40 * mm, 40 * mm, 90 * mm], size=7))

    # ---------------- Page 8-9: clinical notification ----------------
    story.append(PageBreak())
    story.append(Paragraph("7. Clinical Notification", H1))
    cn = qr.get("clinical_notification", {}) or {}
    story.append(Paragraph(f"<b>{fmt(cn.get('title'))}</b>", BODY))
    story.append(Paragraph(f"<b>Risk summary:</b> {fmt(cn.get('risk_summary'))}", BODY))
    story.append(Paragraph(
        f"Overall PSC count: {fmt(cn.get('overall_psc_count'))} of "
        f"{fmt(cn.get('total_cells_analysed'))} cells; confidence: {fmt(cn.get('confidence'))}.",
        BODY))
    story.append(Spacer(1, 3 * mm))
    sites = cn.get("teratoma_risk_sites", []) or []
    half = (len(sites) + 1) // 2
    story.append(_tbl(
        [["Site", "Layer", "Abs. risk", "Level", "Confirmatory assay"]] +
        [[fmt(x.get("anatomical_site")), fmt(x.get("germ_layer")),
          fmt(x.get("absolute_risk_probability")), fmt(x.get("risk_level")),
          fmt(x.get("confirmatory_assay"))[:110]] for x in sites[:half]],
        widths=[28 * mm, 20 * mm, 18 * mm, 18 * mm, 86 * mm], size=6.5))
    if len(sites) > half:
        story.append(PageBreak())
        story.append(Paragraph("7.1 Clinical Notification (continued)", H2))
        story.append(_tbl(
            [["Site", "Layer", "Abs. risk", "Level", "Confirmatory assay"]] +
            [[fmt(x.get("anatomical_site")), fmt(x.get("germ_layer")),
              fmt(x.get("absolute_risk_probability")), fmt(x.get("risk_level")),
              fmt(x.get("confirmatory_assay"))[:110]] for x in sites[half:]],
            widths=[28 * mm, 20 * mm, 18 * mm, 18 * mm, 86 * mm], size=6.5))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Disclaimer:</b> {fmt(cn.get('disclaimer'))}", SMALL))

    # ---------------- Page 10: disease site probabilities ----------------
    story.append(PageBreak())
    story.append(Paragraph("8. Disease Site Probabilities", H1))
    dsp = qr.get("disease_site_probabilities", {}) or {}
    story.append(_tbl([
        ["Total sites", "High", "Moderate", "Low", "Negligible"],
        [fmt(dsp.get("total_sites_evaluated")), fmt(dsp.get("high_risk_sites")),
         fmt(dsp.get("moderate_risk_sites")), fmt(dsp.get("low_risk_sites")),
         fmt(dsp.get("negligible_risk_sites"))],
    ], widths=[34 * mm] * 5))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Formula:</b> {fmt(dsp.get('formula'))}", SMALL))
    story.append(Paragraph(f"<b>Priors source:</b> {fmt(dsp.get('priors_source'))[:300]}", SMALL))

    # ---------------- Page 11: recommendations ----------------
    story.append(PageBreak())
    story.append(Paragraph("9. Recommendations", H1))
    recs = qr.get("recommendations", []) or []
    story.append(_tbl(
        [["#", "Priority", "Category", "Action", "Rationale", "Owner", "Effort"]] +
        [[fmt(i + 1), fmt(r.get("priority")), fmt(r.get("category")),
          fmt(r.get("action"))[:90], fmt(r.get("rationale"))[:110],
          fmt(r.get("owner")), fmt(r.get("effort"))] for i, r in enumerate(recs)],
        widths=[8 * mm, 15 * mm, 25 * mm, 45 * mm, 45 * mm, 20 * mm, 20 * mm], size=6.5))

    # ---------------- Page 12: methodology ----------------
    story.append(PageBreak())
    story.append(Paragraph("10. Methodology", H1))
    me = qr.get("methodology", {}) or {}
    story.append(Paragraph("10.1 Software versions", H2))
    mv = me.get("model_versions", {}) or {}
    story.append(_tbl([["Package", "Version"]] + [[k, fmt(v)] for k, v in mv.items()],
                      widths=[60 * mm, 110 * mm], size=7))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("10.2 Pipeline (10 steps)", H2))
    for step in me.get("pipeline", []) or []:
        story.append(Paragraph(fmt(step), SMALL))
    dims = me.get("input_dimensions", {}) or {}
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        f"Input dimensions: {fmt(dims.get('cells'))} cells x {fmt(dims.get('genes'))} genes; "
        f"decision threshold {fmt(me.get('decision_threshold'))}; seed {fmt(me.get('random_seed'))}.",
        BODY))

    # ---------------- Page 13: per-cell table + heatmap ----------------
    story.append(PageBreak())
    story.append(Paragraph("11. Per-cell Summary (top 25)", H1))
    pcs = qr.get("per_cell_summary", []) or []
    story.append(_tbl(
        [["Cell ID", "PSC probability", "Pluripotency score", "Lineage"]] +
        [[fmt(c.get("cell_id"))[:28], fmt(c.get("psc_probability")),
          fmt(c.get("pluripotency_score")), fmt(c.get("teratoma_lineage"))]
         for c in pcs[:25]],
        widths=[50 * mm, 40 * mm, 40 * mm, 40 * mm], size=7))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("11.1 Gene heatmap (top 10 cells)", H2))
    gh = qr.get("gene_heatmap", {}) or {}
    genes = gh.get("genes", []) or []
    top = gh.get("top_cells", [])[:10] or []
    if genes and top:
        hdr = ["Cell"] + [fmt(g)[:8] for g in genes]
        rows = [[fmt(c.get("cell_id"))[:14]] + [fmt(v, 2) for v in (c.get("values") or [])]
                for c in top]
        story.append(_tbl([hdr] + rows, widths=[26 * mm] + [18 * mm] * len(genes), size=6))

    # ---------------- Page 14: disclaimer + citation + signature ----------------
    story.append(PageBreak())
    story.append(Paragraph("12. Disclaimer, Citation and Signatures", H1))
    dc = qr.get("disclaimer", {}) or {}
    story.append(Paragraph(f"<b>Primary:</b> {fmt(dc.get('primary'))}", BODY))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("12.1 Limitations", H2))
    for lim in dc.get("limitations", []) or []:
        story.append(Paragraph(f"• {fmt(lim)}", SMALL))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"<b>Wet-lab confirmation:</b> {fmt(dc.get('wet_lab_confirmation'))}", BODY))
    story.append(Paragraph(f"<b>Decision authority:</b> {fmt(dc.get('decision_authority'))}", BODY))
    story.append(Paragraph(f"<b>Audit trail:</b> {fmt(dc.get('audit_trail'))}", BODY))
    story.append(Spacer(1, 4 * mm))
    cb = qr.get("citation_block", {}) or {}
    story.append(Paragraph("12.2 Citation", H2))
    story.append(Paragraph(f"<b>Citation:</b> {fmt(cb.get('citation_text'))}", BODY))
    story.append(Paragraph(f"<b>DOI:</b> {fmt(cb.get('doi_placeholder'))}", SMALL))
    story.append(Paragraph(f"<b>License:</b> {fmt(cb.get('license'))}", SMALL))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("12.3 Electronic signature block (21 CFR Part 11)", H2))
    story.append(_tbl([
        ["Role", "Name", "Signature", "Date (UTC)"],
        ["Prepared by (system)", "resipsc automated QC pipeline", "unsigned (RUO)", fmt(rm.get("generated_at_utc"))],
        ["Reviewed by (QA)", "", "", ""],
        ["Approved by (QP)", "", "", ""],
    ], widths=[38 * mm, 55 * mm, 40 * mm, 37 * mm]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "This document was generated automatically by resipsc v2.0.0 and is a "
        "demonstration artifact for a hybrid-trained model. Research Use Only — "
        "NOT FDA-cleared.", SUB))

    doc.build(story)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="path to QC report JSON")
    parser.add_argument("--out", required=True, help="output PDF path")
    args = parser.parse_args()

    with open(args.report, "r", encoding="utf-8") as fh:
        qr = json.load(fh)
    out = build_pdf(qr, args.out)
    print(json.dumps({"status": "ok", "pdf": out,
                     "size_kb": round(os.path.getsize(out) / 1024, 1)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
