import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#4A5568"))
        
        # Header (Pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 755, "CRIE-AF / RESiPSC VALIDATION & CORRELATION REPORT")
            self.drawRightString(letter[0] - 54, 755, "Confidential - Scientific Report")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, 747, letter[0] - 54, 747)

        # Footer (All pages)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(54, 45, letter[0] - 54, 45)
        
        self.drawString(54, 32, "CRIE-AF Single-Cell Screening Benchmark | Model Correlation Assessment")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(letter[0] - 54, 32, page_text)
        self.restoreState()

def generate_report():
    pdf_filename = "CRIE_AF_Model_Correlation_Report.pdf"
    doc = SimpleDocTemplate(
        pdf_filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569'),
        spaceAfter=15
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )

    tbl_hdr = ParagraphStyle(
        'TblHdr',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    tbl_cell = ParagraphStyle(
        'TblCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#1E293B')
    )

    tbl_cell_bold = ParagraphStyle(
        'TblCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#1E293B')
    )

    tag_pos = ParagraphStyle(
        'TagPos',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#047857')
    )

    tag_neg = ParagraphStyle(
        'TagNeg',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor('#B91C1C')
    )

    callout_style = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#1E3A8A')
    )

    story = []

    # Title & Metadata Banner
    story.append(Paragraph("CRIE-AF / RESiPSC Single-Cell Pipeline Report", title_style))
    story.append(Paragraph("Dataset Classification Audit, Model Output Correlation & Biological Validation", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284C7'), spaceBefore=0, spaceAfter=12))

    # Executive Summary Card Table
    summary_data = [
        [
            Paragraph("<b>Model Architecture:</b> RBF-SVM (1,000 Features)", body_style),
            Paragraph("<b>Training Balanced Acc:</b> 98.71%", body_style)
        ],
        [
            Paragraph("<b>Total Reference Cells:</b> 17,360 (5 Pos, 39 Neg)", body_style),
            Paragraph("<b>Unknown Cells Evaluated:</b> 3,961 cells", body_style)
        ],
        [
            Paragraph("<b>Query Sample:</b> Adult Cardiac Neuronal Cells", body_style),
            Paragraph("<b>Validation Outcome:</b> <b>CORRECT & CONCORDANT</b>", body_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[250, 254])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Section 1: Executive Findings
    story.append(Paragraph("1. Executive Technical Correlation & Verdict", h2_style))
    story.append(Paragraph(
        "<b>Biological Question:</b> Did the classifier correctly evaluate the query sample based on the training datasets fed?<br/>"
        "<b>Findings:</b> Yes. The model successfully separated undifferentiated pluripotent stem cells (day 0 hESC/hiPSC) from differentiated controls and somatic tissues. When presented with adult human heart neuronal cells (<i>004_Neuronal_Cells_of_the_adult_human_heart...h5ad</i>, 3,961 cells), the pipeline predicted <b>99.62% (3,946 cells) as Negative</b> and only <b>0.38% (15 cells) as Positive-like</b> (mean score: 0.0102). This aligns with the near-complete absence of core pluripotency markers (<i>NANOG</i>: 0.08%, <i>POU5F1</i>: 0.38%) and strong detection of mature cardiac markers (<i>TNNT2</i>: 22.19%, <i>TNNI3</i>: 13.94%).",
        body_style
    ))
    story.append(Spacer(1, 10))

    # Section 2: Marker Expression Table
    story.append(Paragraph("2. Unknown Sample Marker Gene Concordance", h2_style))
    marker_data = [
        [Paragraph("Gene Symbol", tbl_hdr), Paragraph("Mean Expression", tbl_hdr), Paragraph("Fraction Detected", tbl_hdr), Paragraph("Biological Lineage", tbl_hdr), Paragraph("Model Expectation & Concordance", tbl_hdr)],
        [Paragraph("POU5F1 (OCT4)", tbl_cell_bold), Paragraph("0.00388", tbl_cell), Paragraph("0.73%", tbl_cell), Paragraph("Pluripotency", tbl_cell), Paragraph("Repressed in somatic tissue (Pass)", tag_pos)],
        [Paragraph("SOX2", tbl_cell_bold), Paragraph("0.03935", tbl_cell), Paragraph("7.19%", tbl_cell), Paragraph("Pluripotency / Neural", tbl_cell), Paragraph("Basal neural/ganglion expression (Pass)", tbl_cell)],
        [Paragraph("NANOG", tbl_cell_bold), Paragraph("0.00081", tbl_cell), Paragraph("0.23%", tbl_cell), Paragraph("Pluripotency", tbl_cell), Paragraph("Virtually absent (Pass)", tag_pos)],
        [Paragraph("LIN28A / ZSCAN10", tbl_cell_bold), Paragraph("<0.00034", tbl_cell), Paragraph("<0.10%", tbl_cell), Paragraph("Pluripotency", tbl_cell), Paragraph("Completely silent (Pass)", tag_pos)],
        [Paragraph("TNNT2 (Troponin T2)", tbl_cell_bold), Paragraph("0.17759", tbl_cell), Paragraph("22.19%", tbl_cell), Paragraph("Cardiac lineage", tbl_cell), Paragraph("Strong cardiac lineage signal (Pass)", tag_pos)],
        [Paragraph("TNNI3 / ACTN2", tbl_cell_bold), Paragraph("0.064 - 0.099", tbl_cell), Paragraph("9.6% - 13.9%", tbl_cell), Paragraph("Cardiac structural", tbl_cell), Paragraph("Somatic cardiac phenotype confirmed (Pass)", tag_pos)],
        [Paragraph("MYH6 / MYH7", tbl_cell_bold), Paragraph("0.068 - 0.087", tbl_cell), Paragraph("10.1% - 12.6%", tbl_cell), Paragraph("Cardiac myosin", tbl_cell), Paragraph("Active adult heart transcription (Pass)", tag_pos)],
    ]
    marker_table = Table(marker_data, colWidths=[100, 75, 75, 95, 159])
    marker_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E293B')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')])
    ]))
    story.append(marker_table)
    story.append(Spacer(1, 14))

    # Section 3: Query Sample Classification Table
    story.append(Paragraph("3. Query Sample Classification Summary", h2_style))
    query_data = [
        [Paragraph("Query Dataset File Name", tbl_hdr), Paragraph("Positive Calls", tbl_hdr), Paragraph("Negative Calls", tbl_hdr), Paragraph("Total Cells", tbl_hdr), Paragraph("Dominant Prediction", tbl_hdr)],
        [
            Paragraph("004_Neuronal_Cells_of_the_adult_human_heart_1009f384-b12d-448e-ba9f-1b7d2ecfbb4e.h5ad", tbl_cell),
            Paragraph("15 (0.38%)", tag_pos),
            Paragraph("3,946 (99.62%)", tag_neg),
            Paragraph("3,961", tbl_cell_bold),
            Paragraph("NEGATIVE (Adult Somatic / Non-iPSC)", tbl_cell_bold)
        ]
    ]
    query_table = Table(query_data, colWidths=[190, 70, 74, 50, 120])
    query_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F1F5F9'))
    ]))
    story.append(query_table)

    story.append(PageBreak())

    # Section 4: Positive Reference Datasets Table
    story.append(Paragraph("4. Positive Reference Datasets (Ground Truth Stem Cells)", h2_style))
    story.append(Paragraph("All 5 candidate stem-cell datasets loaded as ground-truth positive references (1,920 cells total):", body_style))
    story.append(Spacer(1, 4))

    pos_data = [
        [Paragraph("Index", tbl_hdr), Paragraph("Dataset Identifier / Sample ID", tbl_hdr), Paragraph("Class", tbl_hdr), Paragraph("Cells", tbl_hdr), Paragraph("Genes", tbl_hdr), Paragraph("Biological Identity", tbl_hdr)],
        [Paragraph("1", tbl_cell), Paragraph("GSM7915977_hESC_d0_replica3_plate1", tbl_cell), Paragraph("POSITIVE", tag_pos), Paragraph("384", tbl_cell), Paragraph("23,851", tbl_cell), Paragraph("Day-0 Human Embryonic Stem Cell (hESC)", tbl_cell)],
        [Paragraph("2", tbl_cell), Paragraph("GSM7915980_hiPSC1_d0_replica1_plate1", tbl_cell), Paragraph("POSITIVE", tag_pos), Paragraph("384", tbl_cell), Paragraph("23,851", tbl_cell), Paragraph("Day-0 Induced Pluripotent Stem Cell 1 (hiPSC1)", tbl_cell)],
        [Paragraph("3", tbl_cell), Paragraph("GSM7915981_hiPSC1_d0_replica2_plate2", tbl_cell), Paragraph("POSITIVE", tag_pos), Paragraph("384", tbl_cell), Paragraph("23,851", tbl_cell), Paragraph("Day-0 Induced Pluripotent Stem Cell 1 (hiPSC1)", tbl_cell)],
        [Paragraph("4", tbl_cell), Paragraph("GSM7915986_hiPSC2_d0_replica2_plate2", tbl_cell), Paragraph("POSITIVE", tag_pos), Paragraph("384", tbl_cell), Paragraph("23,851", tbl_cell), Paragraph("Day-0 Induced Pluripotent Stem Cell 2 (hiPSC2)", tbl_cell)],
        [Paragraph("5", tbl_cell), Paragraph("GSM7915987_hiPSC2_d0_replica3_plate1", tbl_cell), Paragraph("POSITIVE", tag_pos), Paragraph("384", tbl_cell), Paragraph("23,851", tbl_cell), Paragraph("Day-0 Induced Pluripotent Stem Cell 2 (hiPSC2)", tbl_cell)],
    ]
    pos_table = Table(pos_data, colWidths=[28, 206, 55, 40, 45, 130])
    pos_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#047857')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#A7F3D0')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F0FDF4')])
    ]))
    story.append(pos_table)
    story.append(Spacer(1, 14))

    # Section 5: Negative Reference Datasets Table
    story.append(Paragraph("5. Negative Reference Datasets (Controls & Somatic Tissues)", h2_style))
    story.append(Paragraph("All 39 negative reference datasets loaded (10 differentiation controls + 29 Tabula Sapiens adult tissue references, 15,440 cells total):", body_style))
    story.append(Spacer(1, 4))

    neg_rows = [
        ("1", "GSM7915978_hESC_d11_replica3_plate1", "NEGATIVE", "384", "23,851", "Differentiation Control (hESC d11)"),
        ("2", "GSM7915979_hESC_d24_replica3_plate1", "NEGATIVE", "384", "23,851", "Differentiation Control (hESC d24)"),
        ("3", "GSM7915982_hiPSC1_d11_replica1_plate1", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC1 d11)"),
        ("4", "GSM7915983_hiPSC1_d11_replica2_plate2", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC1 d11)"),
        ("5", "GSM7915984_hiPSC1_d24_replica1_plate1", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC1 d24)"),
        ("6", "GSM7915985_hiPSC1_d24_replica2_plate2", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC1 d24)"),
        ("7", "GSM7915988_hiPSC2_d11_replica2_plate2", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC2 d11)"),
        ("8", "GSM7915989_hiPSC2_d11_replica3_plate1", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC2 d11)"),
        ("9", "GSM7915990_hiPSC2_d24_replica2_plate2", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC2 d24)"),
        ("10", "GSM7915991_hiPSC2_d24_replica3_plate1", "NEGATIVE", "384", "23,851", "Differentiation Control (hiPSC2 d24)"),
        ("11", "49312f8c-a75a-4672-9c8a-9078acd35bdb.h5ad", "NEGATIVE", "400", "32,383", "Adult Somatic Reference"),
        ("12", "Bladder_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Bladder (Tabula Sapiens)"),
        ("13", "Blood_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Blood (Tabula Sapiens)"),
        ("14", "Bone_Marrow_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Bone Marrow (Tabula Sapiens)"),
        ("15", "Ear_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Ear (Tabula Sapiens)"),
        ("16", "Eye_TSP1_30_version2d_10X_smartseq_scvi_updated.h5ad", "NEGATIVE", "400", "61,806", "Adult Eye (Tabula Sapiens)"),
        ("17", "Fat_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Adipose/Fat (Tabula Sapiens)"),
        ("18", "Heart_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Heart (Tabula Sapiens)"),
        ("19", "Kidney_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Kidney (Tabula Sapiens)"),
        ("20", "Large_Intestine_TSP1_30_version2d_10X_smartseq.h5ad", "NEGATIVE", "400", "61,806", "Adult Large Intestine (Tabula Sapiens)"),
        ("21", "Liver_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Liver (Tabula Sapiens)"),
        ("22", "Lung_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Lung (Tabula Sapiens)"),
        ("23", "Lymph_Node_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Lymph Node (Tabula Sapiens)"),
        ("24", "Mammary_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Mammary (Tabula Sapiens)"),
        ("25", "Muscle_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Muscle (Tabula Sapiens)"),
        ("26", "Ovary_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Ovary (Tabula Sapiens)"),
        ("27", "Pancreas_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Pancreas (Tabula Sapiens)"),
        ("28", "Prostate_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Prostate (Tabula Sapiens)"),
        ("29", "Salivary_Gland_TSP1_30_version2d_10X_smartseq.h5ad", "NEGATIVE", "400", "61,806", "Adult Salivary Gland (Tabula Sapiens)"),
        ("30", "Skin_TSP1_30_version2d_10X_smartseq_scvi_updated.h5ad", "NEGATIVE", "400", "61,806", "Adult Skin (Tabula Sapiens)"),
        ("31", "Small_Intestine_TSP1_30_version2d_10X_smartseq.h5ad", "NEGATIVE", "400", "61,806", "Adult Small Intestine (Tabula Sapiens)"),
        ("32", "Spleen_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Spleen (Tabula Sapiens)"),
        ("33", "Stomach_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Stomach (Tabula Sapiens)"),
        ("34", "Testis_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Testis (Tabula Sapiens)"),
        ("35", "Thymus_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Thymus (Tabula Sapiens)"),
        ("36", "Tongue_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Tongue (Tabula Sapiens)"),
        ("37", "Trachea_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Trachea (Tabula Sapiens)"),
        ("38", "Uterus_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Uterus (Tabula Sapiens)"),
        ("39", "Vasculature_TSP1_30_version2d_10X_smartseq_scvi.h5ad", "NEGATIVE", "400", "61,806", "Adult Vasculature (Tabula Sapiens)"),
    ]

    neg_data = [[
        Paragraph("No.", tbl_hdr),
        Paragraph("Dataset Identifier / File Name", tbl_hdr),
        Paragraph("Class", tbl_hdr),
        Paragraph("Cells", tbl_hdr),
        Paragraph("Genes", tbl_hdr),
        Paragraph("Biological Identity / Tissue Origin", tbl_hdr)
    ]]

    for r in neg_rows:
        neg_data.append([
            Paragraph(r[0], tbl_cell),
            Paragraph(r[1], tbl_cell),
            Paragraph(r[2], tag_neg),
            Paragraph(r[3], tbl_cell),
            Paragraph(r[4], tbl_cell),
            Paragraph(r[5], tbl_cell)
        ])

    neg_table = Table(neg_data, colWidths=[24, 210, 55, 36, 45, 134])
    neg_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#B91C1C')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#FECACA')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#FFFFFF'), colors.HexColor('#FEF2F2')])
    ]))
    story.append(neg_table)

    # Build PDF with dynamic 2-pass numbering
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated {pdf_filename}")

if __name__ == '__main__':
    generate_report()
