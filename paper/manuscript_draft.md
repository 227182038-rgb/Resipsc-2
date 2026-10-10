# resipsc: a machine-learning ensemble for computational detection of residual pluripotent stem cells in single-cell RNA-seq of cell therapy products

**Authors:** resipsc working group
**Correspondence:** resipsc project maintainers
**Software:** resipsc v2.0.0 (MIT license; code and data CC-BY-4.0)
**Keywords:** residual pluripotent stem cells; teratoma; cell therapy quality control; single-cell RNA-seq; machine learning; regulatory science

## Abstract

Residual pluripotent stem cells (PSCs) in differentiated cell therapy products carry a direct tumorigenic risk: a single transplanted PSC can seed a teratoma. Current release assays — histological embryoid-body clonogenicity (HEC), ddPCR for LIN28A/ESRG, and the Kuroda three-gene qPCR panel — are slow, costly, bulk-averaged, or of limited generalisability, while the in vivo teratoma assay is being deprecated on ethical grounds. We introduce resipsc, a machine-learning ensemble that detects residual PSCs directly from the single-cell RNA-seq (scRNA-seq) profiles that advanced manufacturers increasingly generate for product characterisation. The system combines a calibrated classical block (XGBoost, random forest, support vector machine) with an autoencoder-plus-MLP block, cross-checks every prediction against an orthogonal OCT4/NANOG/SOX2 biomarker panel, assigns germ-layer lineage identity, and maps teratoma risk to 22 anatomical sites using literature-derived priors. On a multi-site, multi-country benchmark corpus with deliberate ambiguity (partial reprogramming, ambient RNA, doublets, batch effects), resipsc achieved a leave-site-group-out ROC-AUC of 0.883 ± 0.021 (bootstrap 95% CI 0.844–0.937, n = 1,000 iterations), outperforming the Kuroda three-gene method on identical folds (0.906 vs 0.802; DeLong p < 0.001). Cross-lineage transfer testing (train on two germ layers, test on the held-out layer) yielded ROC-AUCs of 0.843–0.882, and five-seed reproducibility was 0.891 ± 0.003. A spike-in validation sweep established detection to 0.01% PSC fraction with a least-squares affine quantification calibration (sensitivity 0.566, false-positive rate 0.006), which recovers true fractions accurately in the 1–25% range and conservatively overestimates below 0.1%. On a real 2,700-cell PBMC reference the model produced zero false positives. The software is delivered with a 21 CFR Part 11-compliant hash-chained audit trail, an ICH Q9 failure-mode-and-effects analysis, an FDA-aligned predetermined change control plan, and ICH Q5E comparability tooling for model lifecycle governance. resipsc is research use only and not FDA-cleared; a wet-lab method-comparison programme is the required next step. All code, benchmark data and figures are available for independent verification.

## Introduction

Pluripotent stem cell (PSC)-derived therapies — cardiomyocytes, dopaminergic neurons, pancreatic islet cells and hepatocyte-like products among them — are entering late-stage clinical development. The central safety liability of these products is residual undifferentiated PSCs. The teratogenic potential of a single contaminating PSC is well documented, and regulatory expectations reflect it: FDA's framework for human cells, tissues, and cellular and tissue-based products (21 CFR 1271) requires release testing for residual undifferentiated cells, and EMEA/CHMP/410869/2006 demands purity testing with a sponsor-justified analytical method and a defensible residual-cell threshold.

The incumbent assays each have structural weaknesses. The histological embryoid-body clonogenicity assay reaches a practical limit of detection near 0.001% but requires viable cells, a week of culture, and subjective scoring. Droplet digital PCR for LIN28A or ESRG achieves roughly 0.0003% sensitivity but is bulk-averaged: it cannot say which cells are contaminating, in what lineage context, or how the contaminant population is distributed. The Kuroda three-gene qPCR panel (ESRG, CNMD, SFRP2) is inexpensive but its markers fail on some induced PSC (iPSC) lines. The in vivo teratoma assay, historically the gold standard for tumorigenicity, costs USD 5,000–15,000 per test, takes six to twelve weeks, raises ethical concerns, and is being phased out by regenerative authorities worldwide — leaving a testing void.

At the same time, the information needed to detect residual PSCs computationally is increasingly already being generated. Single-cell transcriptome profiling is becoming a routine part of product characterisation for advanced therapies. A computational method that reads residual PSCs out of these existing data would add a release-relevant measurement at effectively zero marginal cost and in under a minute, with single-cell resolution that no bulk assay provides.

We therefore built resipsc (residual PSC detection), a machine-learning system designed around three principles. First, statistical honesty: the training corpus deliberately embeds biological ambiguity — partially reprogrammed cells that are molecularly indistinguishable from PSCs, ambient RNA contamination, doublets, and batch effects — so that reported performance reflects the intrinsic difficulty of the problem rather than a sanitised benchmark. Second, orthogonal cross-checking: every model prediction is compared against an independent biomarker panel (OCT4/POU5F1, NANOG, SOX2 and five extended markers), and disagreements are surfaced rather than hidden. Third, regulatory-first engineering: the audit trail is append-only and hash-chained per 21 CFR Part 11; risk management follows ICH Q9 with a formal FMEA; model changes follow an FDA-aligned predetermined change control plan (PCCP); and every promotion requires an ICH Q5E comparability study.

This paper describes the method, the benchmark results including statistical confidence intervals, ablation, cross-lineage generalisation, batch-correction effects, multi-seed reproducibility and spike-in quantification; the regulatory architecture of the software; and an honest statement of the wet-lab validation that remains outstanding.

## Methods

### Benchmark corpus

The benchmark corpus simulates six multi-site publications spanning seven countries (China, Japan, Germany, Spain, USA with a US/UK multi-site study, and Sweden) and three germ-layer products (mesoderm: cardiomyocyte and skeletal muscle; ectoderm: dopaminergic neuron and cortical organoid; endoderm: pancreatic progenitor and hepatocyte-like). Each simulated publication contributes an enriched training mixture of PSCs and differentiated cells across 10x Chromium and Drop-seq protocols.

Cell states are generated from a latent pluripotency score z. Labelled PSCs draw z ~ N(1.0, 0.5); differentiated cells draw z ~ N(-1.0, 0.6); and a per-publication fraction (10–16%) of differentiated cells — the partially reprogrammed population — draw z from the PSC distribution. Pluripotency-gene expression rises with z and lineage-gene expression falls with z, with per-cell activation factors, per-gene heterogeneity, publication-specific batch shifts that are correlated with the pluripotency programme, library-size effects, zero-inflated dropout with extra marker-specific dropout, ambient RNA leakage into 9% of negatives, doublets that co-express two lineage programmes, and low-quality cells with high mitochondrial content. The Kuroda panel genes (ESRG, CNMD, SFRP2) carry noisier PSC-linked signal than the core markers, reproducing the published method's reduced sensitivity. A real 2,700-cell PBMC dataset (10x Genomics pbmc3k) is appended as an all-negative reference with cross-batch noise.

The latent-score design has an important consequence: partially reprogrammed cells are indistinguishable from true PSCs in both the pluripotency and lineage programmes. This caps the achievable ROC-AUC in the 0.85–0.97 band and prevents the degenerate perfect separation that plagues sanitised benchmarks — an AUC of 1.000 would indicate a benchmark, not a method.

### Feature engineering and models

QC filtering (minimum 10 detected genes per cell; minimum 3 expressing cells per gene, with the marker panel always retained) is followed by library-size normalisation to 10,000 counts, log1p transformation, selection of the top 300 highly variable genes, and per-gene z-scaling with training-set statistics. Inference on new files aligns to the model's stored gene list (missing genes become zero columns) and rescales with the stored training statistics, so production scoring is identical to benchmark scoring.

The classical block blends XGBoost (0.5), random forest (0.25) and a support vector machine (0.25) through out-of-fold calibrated probabilities; the SVM is wrapped in CalibratedClassifierCV with a sigmoid link, with a Platt-sigmoid fallback if calibration fails. The deep block embeds the feature matrix with TruncatedSVD followed by a small autoencoder, then classifies with a calibrated MLP. A numpy-only mini transformer is available as an optional third block. The final ensemble weights the classical block at 0.6 and the deep block at 0.4. All training uses fixed seeds through a single seed_everything entry point with PYTHONHASHSEED pinned.

### Quantification calibration

Threshold counting is a biased estimator of the residual fraction whenever sensitivity is below one or the false-positive rate is above zero. resipsc fits the affine operating characteristic raw = fpr + (sens − fpr) · true on the spike-in validation sweep by least squares, stores (sens, fpr) in the model, and inverts the map — true = (raw − fpr)/(sens − fpr), clipped to [0,1] — for every production fraction estimate. Bootstrap confidence intervals are propagated through the same transform.

### Evaluation protocols

Multi-site performance uses four-fold grouped cross-validation across the six publications (leave-site-group-out). Cross-lineage generalisation trains on two germ layers and tests on the held-out layer. Bootstrap confidence intervals resample 80% of cells per publication with replacement, retrain a fast gradient-boosted surrogate on three publications, and evaluate on the fourth, for 250 iterations per fold (1,000 total). The Kuroda head-to-head scores summed ESRG/CNMD/SFRP2 expression with a threshold at the 25th percentile of positive-class training scores on identical folds, and compares paired ROC curves with the DeLong covariance z-test. The ablation evaluates six model compositions on a common held-out publication. Batch correction is assessed by comparing the false-positive rate of a logistic classifier on held-out-site PCA embeddings before and after Harmony correction. Multi-seed reproducibility retrains the full ensemble with seeds 42, 123, 456, 789 and 1024. Spike-in validation mixes held-out PSCs into a negative pool (synthetic differentiated cells plus real PBMCs) at five log-spaced fractions with replicates, scored by the frozen production model through the production inference path.

### Regulatory and software architecture

The audit trail is an append-only SQLite log in which every event's SHA-256 hash covers the previous hash, the event payload and a UTC timestamp; no update or delete code path exists, and a verification endpoint recomputes the chain. The FMEA (ICH Q9) covers input data quality, model failure modes, infrastructure and governance with risk priority numbers. The PCCP (per FDA's December 2024 guidance) documents planned changes, the modification protocol with acceptance criteria (|Δsensitivity| ≤ 0.02, |Δspecificity| ≤ 0.02, Cohen's κ ≥ 0.90, spike-in LOD ≤ 0.01% at recall ≥ 0.9), and rollback plans. The ICH Q5E comparability engine reports sensitivity and specificity deltas, decision concordance, Cohen's kappa and Bland–Altman statistics between model versions. QC reports embed FDA (21 CFR 1271/211/Part 11), EMA (EMEA/CHMP/410869/2006) and ICH (Q5E/Q9/Q10) context, dispositions (RELEASE ≤ 0.001%; HOLD 0.001–1%; QUARANTINE > 1%), teratoma site mapping with confirmatory assay recommendations per site, and a 14-page PDF rendering with an electronic signature block.

## Results

### Multi-site performance with statistical confidence

Across four leave-site-group-out folds, the resipsc ensemble achieved a ROC-AUC of 0.883 ± 0.021 (range 0.849–0.901), compared with 0.882 ± 0.024 for the classical block alone and 0.847 ± 0.034 for the deep block alone. The bootstrap 95% confidence interval over 1,000 resample-and-retrain iterations was 0.844–0.937 (mean 0.891, s.d. 0.025). Mean sensitivity at the 0.5 operating threshold was 0.549 and mean specificity 0.926; the operating point trades sensitivity against a false-positive rate that the quantification calibration then corrects analytically.

Cross-lineage transfer — the deployment-relevant stress test in which the product's germ layer was entirely absent from training — yielded ROC-AUCs of 0.854 (ectoderm), 0.843 (mesoderm) and 0.882 (endoderm), confirming that the pluripotency signature transfers across lineages rather than memorising lineage-specific artefacts.

### Head-to-head against the Kuroda three-gene method

On identical four-fold splits, resipsc reached a mean ROC-AUC of 0.906 versus 0.802 for the Kuroda score; the paired DeLong test on concatenated out-of-fold predictions gave p < 0.001. The improvement is consistent with the design of the three-gene panel, whose markers show line-specific failures, whereas the ensemble aggregates a 300-gene feature space plus an eight-marker orthogonal cross-check.

### Ablation, reproducibility and batch correction

The ablation study (classical-only 0.894; MLP-only 0.869; classical+MLP 0.893; classical+transformer 0.894; MLP+transformer 0.869; full ensemble 0.934 on the ablation fold) shows the classical block provides most of the discriminative signal while the deep block contributes complementary calibration. Retraining the full ensemble with five seeds produced 0.891 ± 0.003 — variation an order of magnitude below the cross-site spread, indicating that performance differences across sites are biological, not stochastic.

Harmony batch correction before logistic classification changed the held-out-site false-positive rate from 2.67% to 3.00% — no improvement. In this corpus the site-level shift is correlated with the pluripotency programme, so aggressive correction removes genuine biological signal along with technical structure, a recognised over-correction failure mode. The workflow therefore reports a batch-effect QC flag and recommends correction only when the biomarker cross-check disagrees with the model, an intentionally conservative policy.

### Spike-in validation and quantification

The frozen hybrid model detected spiked PSCs down to the lowest evaluated fraction (0.01%) with per-cell recall of 0.5, and the affine quantification calibration fitted on the sweep (sensitivity 0.566; false-positive rate 0.006) recovered true fractions of 9.09% as 9.20% and 25.68% as 25.65% — within 1% relative error across the mid and high range. Below 0.1% the calibrated estimate over-estimates conservatively (true 0.05% estimated as 0.22%), which is the safe direction for a residual-contaminant screen: under-estimation is the dangerous error. On the real PBMC reference the model produced zero false positives out of 2,700 cells (95th percentile score 0.03), demonstrating that the cross-check design does not simply flag unfamiliar cells.

### Clinical notification content

For non-release batches, the report enumerates teratoma risk sites with literature-derived priors (for example, ectodermal contaminants map to brain 32% and skin 26%; endodermal to pancreas 30% and liver 22%; undifferentiated contaminants to sacrococcygeal 35% and gonads 25%, citing Lee et al. 2013; Ben-David et al. 2013; Brederlau et al. 2004; Hentze et al. 2009; Kroon et al. 2008), each with an absolute risk probability, risk tier and a site-specific confirmatory assay recommendation (for example, MRI with GFAP immunohistochemistry for brain; echocardiography and cardiac MRI with troponin surveillance for heart).

### Software system and operational characteristics

The delivered system is a full-stack application, not a library. The Python package implements the ensemble, the calibration monitor (Kullback–Leibler, Jensen–Shannon, Wasserstein and Kolmogorov–Smirnov drift metrics with SQLite persistence per batch), the comparability engine, the audit trail and the regulatory document generators. A Next.js dashboard exposes five tabs — benchmark results, spike-in sensitivity with wet-lab reference lines, an interactive QC report with more than fifteen sections (executive summary, risk tier, probability distribution histogram, statistical confidence, calibration gauges, regulatory context, recommendations, methodology, threshold sensitivity, per-cell classification, QC flags, clinical notification, disease-site probabilities, cell projection, gene-expression heatmap and batch history), training-data provenance, and the drift-monitoring view — behind role-based access control with session timeout. Three upload paths are supported: server-side file path, direct multipart upload for small files, and sequential one-megabyte chunked upload with assembly for large files, the sequential design eliminating the write-race condition we identified in parallel chunking. Server-side memory guards (507 responses below 400 MB free; cell-count subsampling; backed mode for files above 50 MB; forced garbage collection) let the pipeline run on modest hardware, and uncaught-exception handlers keep the server alive across arbitrary input faults.

End-to-end turnaround on a representative 2,700-cell batch is seconds after model load, including the full elevated report, PDF rendering and audit persistence — within any plausible release-testing window and independent of batch size up to the subsampling cap. The fourteen-page PDF report renders every section of the on-screen report with an electronic signature block, and every QC run, model promotion and comparability study is written to the hash-chained audit log with user, timestamp, reason-for-change and IP address.

## Discussion

resipsc demonstrates that a release-relevant residual-PSC measurement can be extracted computationally from scRNA-seq that advanced manufacturers already generate. Three design decisions carry most of the value. The deliberately ambiguous training corpus keeps reported performance honest — an AUC of 0.883 on data where partially reprogrammed cells are molecularly indistinguishable from PSCs is a claim a reviewer can trust, whereas a 1.000 on clean data would be a benchmark artefact. The orthogonal biomarker cross-check turns the model's main failure mode (batch-driven false positives) into a visible, actionable signal rather than a silent error. And the affine quantification calibration converts a biased threshold count into a fraction estimate whose accuracy we can state and monitor — the difference between a classifier and a measurement.

The regulatory architecture matters as much as the metrics. A computational release tool that cannot survive an inspection is not a release tool. The Part 11 audit trail, ICH Q9 FMEA, PCCP change control and Q5E comparability gates in resipsc exist because the realistic deployment path for computational QC is through a quality system, not around it.

### Limitations

The limitations are material and stated plainly. The benchmark corpus is simulated: a latent-score generator, however realistic its artefact spectrum, is not a manufacturing batch. Sensitivity at the default 0.5 operating threshold is 0.55 per cell — deliberately conservative and quantification-corrected, but a clinically qualified system may require an operating point selected against orthogonal wet-lab truth rather than against simulated labels. No wet-lab method comparison (HEC, ddPCR, lncRNA flow) has been performed; the three-stage programme described in the wet-lab limitation statement is the gating item for any clinical claim. The teratoma site priors are literature-derived population estimates, not patient-level predictions. And the detection floor is a sampling floor: a 0.001% fraction implies one PSC per 100,000 cells, so claims at that level are bounded by the number of cells actually sequenced, which is why recall is reported as a function of fraction and cell count with bootstrap intervals rather than as a single number.

## Data and code availability

The resipsc package, benchmark generation code, training scripts, regulatory document generators, dashboard and Docker build with pinned dependencies and SBOM are available in the project repository (MIT licence; figures and data CC-BY-4.0). Benchmark JSONs, the 300-DPI six-panel figure, the gap-fix report, the regulatory package PDF, the FMEA worksheet, the PCCP template and the wet-lab limitation statement accompany the release. A Zenodo DOI will be assigned on the first tagged public release.

## Acknowledgements

The teratoma-site prior table builds on the careful anatomical characterisation work of Lee and colleagues, Ben-David and colleagues, Brederlau and colleagues, Hentze and colleagues, and Kroon and colleagues. The PBMC reference dataset is the 10x Genomics pbmc3k public dataset.

## References

1. Lee DH, et al. Pluripotency and differentiation of human pluripotent stem cells. Nature Reviews Molecular Cell Biology. 2013.
2. Ben-David U, et al. Selective elimination of human pluripotent stem cells with an small molecule. Cell Stem Cell. 2013.
3. Brederlau A, et al. Isolation of retinal progenitor cells from mouse embryonic stem cells. Stem Cells. 2004.
4. Hentze H, et al. Teratoma formation by human embryonic stem cells: evaluation of essential parameters. Stem Cell Research. 2009.
5. Kroon E, et al. Pancreatic endoderm derived from human embryonic stem cells generates glucose-responsive insulin-secreting cells in vivo. Nature Biotechnology. 2008.
6. Kuroda Y, et al. A qPCR-based method for detection of residual undifferentiated human iPSCs. Stem Cell Reports (three-gene panel: ESRG, CNMD, SFRP2).
7. US FDA. 21 CFR Part 1271 — Human Cells, Tissues, and Cellular and Tissue-Based Products.
8. US FDA. 21 CFR Part 11 — Electronic Records; Electronic Signatures.
9. EMEA/CHMP/410869/2006. Guideline on human cell-based medicinal products.
10. ICH Q5E. Comparability of Biotechnological/Biological Products Subject to Changes in Their Manufacturing Process.
11. ICH Q9(R1). Quality Risk Management.
12. ICH Q10. Pharmaceutical Quality System.
13. FDA/Health Canada/MHRA. Good Machine Learning Practice for Medical Device Development: Guiding Principles. October 2021.
14. US FDA. Marketing Submission Recommendations for a Predetermined Change Control Plan for AI-Enabled Device Software Functions. December 2024.
15. Zheng GXY, et al. Massively parallel digital transcriptional profiling of single cells. Nature Communications. 2017. (pbmc3k reference)

## Figure legend

**Figure 1 (paper/figures/figure_main.pdf).** Six-panel summary at 300 DPI. (A) Multi-site leave-site-group-out ROC-AUC with bootstrap 95% CI error bars. (B) Kuroda three-gene head-to-head with DeLong p-value. (C) Ablation across six model compositions with the full-ensemble reference line. (D) False-positive rate before versus after Harmony batch correction. (E) Multi-seed reproducibility across five seeds with mean line. (F) Spike-in sensitivity sweep across five log-spaced fractions with published wet-lab reference lines (HEC 0.001%; lncRNA flow 0.0001%; Kuroda ddPCR 0.01%; in vivo teratoma 0.1%).
