# Predetermined Change Control Plan (PCCP) — resipsc

**Model:** resipsc-ensemble-2.0.0  
**Guidance:** FDA guidance: Marketing Submission Recommendations for a Predetermined Change Control Plan for AI-Enabled Device Software Functions (Dec 2024)  
**Retrain trigger:** Calibration drift (KL > 0.10 or KS > 0.15) on two consecutive batches, or annual review

## Section 1 — Description of Planned Changes

### PC-01 — Model weights

- **Planned modification:** Periodic retraining on the accumulated QC corpus (new synthetic + real batches)
- **Frequency:** Annual or drift-triggered
- **Risk:** Performance regression on previously released product types

### PC-02 — Feature space

- **Planned modification:** Expansion of the highly-variable gene set (300 -> 500) with re-validated benchmarks
- **Frequency:** Rare, versioned
- **Risk:** Distribution shift in score calibration

### PC-03 — Decision thresholds

- **Planned modification:** Recalibration of the 0.5 decision threshold against new spike-in data
- **Frequency:** With each retrain
- **Risk:** Altered release/quarantine boundaries

### PC-04 — Site prior table

- **Planned modification:** Update teratoma site priors when new epidemiological literature is published
- **Frequency:** Rare, literature-driven
- **Risk:** Changed clinical notification content

Out of scope:
- Changes to intended use or indications
- Changes to the clinical claim (residual PSC detection)
- Architecture swaps that alter the intended-use statement

## Section 2 — Modification Protocol

**Data requirements.** Retraining corpus must include all production QC batches since the last promotion, plus the frozen golden dataset (>= 100 representative samples spanning lineages and spike-in ratios).

**Retraining procedure:**

1. Freeze current model snapshot + model card hash (rollback anchor)
2. Retrain on expanded corpus with fixed random seeds
3. Re-run multi-site CV, cross-lineage CV and spike-in sweep
4. Run ICH Q5E comparability vs current model on the golden dataset
5. Emit PCCP-delta document and updated model card
6. QA approval gate; audit-logged promotion; update registry

**Acceptance criteria:**

| Criterion | Threshold |
|-----------|-----------|
| roc_auc | >= 0.90 on multi-site CV (mean over folds) |
| sensitivity_delta | <= 0.02 vs current model (golden dataset) |
| specificity_delta | <= 0.02 vs current model (golden dataset) |
| cohens_kappa | >= 0.90 decision concordance vs current model |
| spikein_lod | <= 0.01% at recall >= 0.9 |
| calibration | Brier < 0.15 and ECE < 0.15 vs biomarker reference |

**Verification.** Automated checks in CI (bootstrap CIs, multi-seed stability across seeds 42/123/456/789/1024, ablation parity); manual QA review of the PCCP-delta document.

## Section 3 — Impact Assessment

**Benefit-risk.** Change management preserves the safety benefit of early residual-PSC detection while controlling regression risk via comparability gates.

**Post-market monitoring.** CalibrationMonitor drift metrics (KL/JS/Wasserstein/KS) tracked per batch; CAPA workflow for two consecutive DRIFTED statuses.

**Rollback plan.** Restore previous model snapshot from the registry, re-run Q5E comparability, and document in the audit trail within 1 business day.

**Records.** All promotions are recorded in db/audit.db with PCCP-delta references.
