# FMEA — residual PSC detection ML system (resipsc v2.0)

**Standard:** ICH Q9(R1) Quality Risk Management  
**Team:** ML engineering, QA, bioinformatics, regulatory affairs  
**Scale:** RPN = Severity (1-10) x Occurrence (1-10) x Detection (1-10); HIGH >= 150, MEDIUM >= 60, LOW < 60  
**Review cycle:** Annually and after any High-severity CAPA or model promotion

## Risk summary

- Failure modes: **12**
- HIGH risk (RPN >= 150): **3**
- MEDIUM risk (60 <= RPN < 150): **6**
- LOW risk (RPN < 60): **3**
- Maximum RPN: **192**

## Worksheet

| ID | Component | Failure mode | Effect | S | O | D | RPN | Class | Controls | Mitigation |
|----|-----------|-------------|--------|---|---|---|-----|-------|----------|-------------|
| FM-02 | Input data | Batch effects between product runs | False-positive PSC calls inflate the estimated fraction | 8 | 6 | 4 | 192 | **HIGH** | Biomarker cross-check warning; Harmony re-scoring pathway | Batch-effect QC flag; cross-check agreement printed on every report |
| FM-01 | Input data | Low cell count (< 200 cells sequenced) | Residual PSC fraction estimate has a wide CI; false RELEASE possible | 9 | 4 | 5 | 180 | **HIGH** | Critical QC flag on reports; recommend minimum 500 cells | Sampling SOP; automated n<200 critical flag blocks auto-RELEASE |
| FM-03 | Input data | Ambient RNA contamination carries marker signal | Non-PSC cells score positive on OCT4/NANOG/SOX2 | 6 | 5 | 6 | 180 | **HIGH** | SoupX-style decontamination upstream recommended | Model-only vs biomarker-only discrepancy counts surfaced in report |
| FM-05 | Model | False-negative: tumorigenic lot released | Patient safety impact — teratoma formation post-transplant | 10 | 2 | 7 | 140 | **MEDIUM** | Conservative decision threshold; spike-in LOD monitoring; binomial test on every report | Hold/Quarantine dispositions above 0.001%; orthogonal confirmation required for release |
| FM-04 | Input data | Doublets simulate PSC gene programmes | Doublet cells classified as PSC -> fraction overestimate | 5 | 5 | 5 | 125 | **MEDIUM** | Scrublet/DoubletFinder upstream; doublet-aware training data | Synthetic doublets included in training corpus |
| FM-08 | Model | Out-of-lineage product (unseen germ layer) | Reduced sensitivity on products outside training distribution | 7 | 3 | 5 | 105 | **MEDIUM** | Cross-lineage CV metrics published on dashboard | Model credentials show lineage AUCs; retrain with new lineages |
| FM-07 | Model | Silent drift of score distribution | Gradual degradation of detection performance | 7 | 4 | 3 | 84 | **MEDIUM** | CalibrationMonitor (KL/JS/Wasserstein/KS) per batch with SQLite persistence | Drift triggers retraining per PCCP; CAPA workflow |
| FM-09 | Infrastructure | Partial file upload / corrupted h5ad | QC run fails or analyses truncated data | 6 | 3 | 4 | 72 | **MEDIUM** | Chunked upload with assembly validation; size checks | Graceful JSON parse errors; server crash protection (instrumentation.ts) |
| FM-06 | Model | False-positive: conforming lot rejected | Costly batch loss and manufacturing delay | 4 | 5 | 3 | 60 | **MEDIUM** | Biomarker cross-check; threshold sensitivity table | QA review pathway (HOLD) rather than auto-reject |
| FM-11 | Governance | Unauthorised model swap without comparability | Undocumented performance change in a regulated workflow | 9 | 2 | 3 | 54 | **LOW** | Model registry + PCCP-delta on retrain; audit-logged promotion | ICH Q5E comparability gate before promotion |
| FM-10 | Infrastructure | Audit trail unavailable (DB lock) | Part 11 non-compliance for affected events | 8 | 2 | 2 | 32 | **LOW** | WAL mode; 30s busy timeout; chain verification endpoint | API returns explicit 503 if audit write fails — fail closed |
| FM-12 | Governance | Privilege escalation / audit tampering | Loss of record integrity (21 CFR Part 11) | 10 | 1 | 2 | 20 | **LOW** | Append-only schema (no UPDATE/DELETE code paths); SHA-256 chain; RBAC | Chain verification API; alert on mismatch |

## Linked documents

- paper/pccp_template.md (change control)
- paper/wet_lab_limitation.md (validation gaps)
- db/audit.db (Part 11 trail)
