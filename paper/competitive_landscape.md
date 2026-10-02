# Competitive Landscape — Residual PSC Detection Methods

## Method comparison

| Method | Sensitivity (LOD) | Cost/sample | Turnaround | Limitations |
|--------|-------------------|-------------|------------|-------------|
| HEC assay (histological embryoid-body / clonogenicity) | 0.001% | $50-200 | 7 days | Labor-intensive; requires viable cells; subjective scoring |
| ddPCR (LIN28A/ESRG) | 0.0003% | $150-500 | 1 day | Bulk only (loses single-cell resolution); $80-150K equipment; some false positives |
| Kuroda qPCR (3-gene: ESRG/CNMD/SFRP2) | 0.01% | $50-150 | 1-2 days | Not generalizable; markers fail on some iPSC lines (confirmed in our head-to-head) |
| In vivo teratoma assay | 0.1-1% | $5,000-15,000 | 6-12 weeks | Ethical concerns; poor quantification; being deprecated globally |
| Flow cytometry (TRA-1-60/SSEA-4) | ~0.01% | $100-300 | 0.5 day | Surface epitope loss in some lines; viability dependent |
| **resipsc (computational)** | **0.01% (validated spike-in; single-cell detection events below this level)** | **$0 marginal** | **< 1 min after model load** | Requires existing scRNA-seq data; Research Use Only (not FDA-cleared); wet-lab validation outstanding |

resipsc figures reflect the current hybrid build: spike-in detection to 0.01% with
quantification-calibrated fraction estimates. If scRNA-seq is already generated as part
of product characterization, the marginal cost of resipsc analysis is effectively zero
and results are available in under a minute — versus 1-12 weeks and $50-15,000 for the
wet-lab alternatives.

## Market gap

**No FDA-cleared computational tool exists for residual PSC detection from scRNA-seq.**
All incumbent methods are wet-lab; none exploits the single-cell transcriptomes that
advanced cell therapy manufacturers already generate for product characterization.
resipsc is the first tool to address this gap directly, and the regulatory pathway
(PCCP, GMLP, ICH Q5E/Q9/Q10, 21 CFR Part 11) is built into the software rather than
retrofitted.

## Market sizing

- Cell therapy market: $4.74B (2023) → $20.07B (2030), CAGR 22.66%
- Cell therapy QC testing segment: $3.11B (2025) → $12.35B (2034)
- Key buyer segments:
  - iPSC therapy companies: BlueRock Therapeutics, Fujifilm Cellular Dynamics, Sana Biotechnology, Fate Therapeutics, Aspect Biosystems
  - CDMOs serving cell therapy: Lonza, Catalent, WuXi ATU, AGC Biologics, Resilience
- Pricing model (B2B SaaS — no CPT code exists, not reimbursable):
  - Per-test: $200-500 per QC analysis
  - Subscription: $50K-250K/year (unlimited batches, validation support, audit trail hosting)

## Competitive positioning

1. **vs HEC/ddPCR/qPCR:** resipsc is complementary at first (triage + orthogonal
   quantification) and becomes primary once clinically validated — the single-cell
   resolution provides lineage and teratoma-site context no bulk assay can.
2. **vs in vivo teratoma assay:** ethically and economically superior; regenerative
   authorities worldwide are deprecating the in vivo assay, leaving a testing void.
3. **vs generic scRNA-seq annotators (Azimuth/CellTypist):** those tools assign cell
   types but do not emit GMP dispositions, quantification calibration, teratoma risk
   mapping, Part 11 audit trails, or model lifecycle governance. resipsc is built
   for the QC workflow, not exploration.

## Barriers to entry for competitors

- Regulatory: PCCP + Part 11 + Q5E comparability infrastructure takes 12-24 months
- Data: labelled residual-PSC manufacturing datasets are extremely scarce
- Trust: clinicians require orthogonal validation studies (the wet-lab programme
  in paper/wet_lab_limitation.md is the long-term moat once executed)

## Risks

- A large incumbent (10x, Illumina, Thermo Fisher) bundles a similar capability
  into their scRNA-seq analysis suites — mitigate via first-mover regulatory clearance
  and CDMO partnerships.
- The in vivo assay is deprecated without replacement mandate — the void may persist
  rather than be filled computationally; mitigate via thought leadership and FDA
  pre-submission engagement.
