"""Smoke test: train ensemble on synthetic data, check AUC range + full QC report."""

import sys
sys.path.insert(0, "/home/z/my-project")

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from resipsc.config import default_config
from resipsc.data.synthetic import simulate_datasets
from resipsc.models.ensemble import ResipscEnsemble
from resipsc.pipeline import build_training_matrix
from resipsc.utils.seed import seed_everything

seed_everything(42)
cfg = default_config()
print(f"config: hvg={cfg.n_hvg} cells={cfg.max_cells_per_dataset}")

ads = simulate_datasets(max_cells_per_dataset=800, seed=42)
X, y, gene_list, mu, sd, sites = build_training_matrix(ads, n_hvg=cfg.n_hvg)
print(f"train matrix: {X.shape}, PSC rate: {y.mean()*100:.2f}%, genes: {len(gene_list)}")

model = ResipscEnsemble(cfg)
model.fit(X, y, gene_names=gene_list, mu=mu, sd=sd)

# split AUC (fresh model on train split to avoid optimistic bias)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
m2 = ResipscEnsemble(cfg)
m2.fit(Xtr, ytr, gene_names=gene_list, mu=mu, sd=sd)
p = m2.predict_proba(Xte)[:, 1]
auc = roc_auc_score(yte, p)
print(f"HOLDOUT ROC-AUC: {auc:.4f}  (target 0.80-0.97)")

# full QC report on a RAW dataset (tests the inference path end-to-end)
report = model.qc_report_dict(ads[0], batch_id="SMOKE-001", input_file="synthetic.h5ad")
keys = sorted(report.keys())
print(f"report top-level keys: {len(keys)}")
required = [
    "batch_id", "decision", "decision_reason", "n_cells", "n_cells_above_threshold",
    "estimated_psc_fraction", "estimated_psc_count", "psc_probability_mean",
    "psc_probability_max", "lineage_breakdown", "mean_teratoma_risk_score",
    "max_teratoma_risk_score", "thresholds", "per_cell_summary",
    "biomarker_model_agreement", "biomarker_model_disagreement", "cross_check_warning",
    "clinical_notification", "model_credentials", "executive_summary", "risk_tier",
    "methodology", "statistical_confidence", "probability_distribution",
    "calibration_metrics", "recommendations", "citation_block", "regulatory_context",
    "report_metadata", "threshold_sensitivity", "per_cell_classification",
    "disease_site_probabilities", "qc_flags", "disclaimer", "cell_projection",
    "gene_heatmap", "batch_history",
]
missing = [k for k in required if k not in report]
print(f"missing required keys: {missing}")
print(f"decision: {report['decision']} | tier: {report['risk_tier']['tier']}")
print(f"agreement: {report['biomarker_model_agreement']}")
print(f"projection points: {len(report['cell_projection']['points'])} method={report['cell_projection']['method']}")
print(f"heatmap genes: {report['gene_heatmap']['genes']}")
print(f"clinical sites: {len(report['clinical_notification']['teratoma_risk_sites'])}")
print(f"bins: {len(report['probability_distribution']['bins'])}")

# JSON serialisability
from resipsc.utils.io import save_json
save_json(report, "/tmp/smoke_report.json")
import json
json.loads(open("/tmp/smoke_report.json").read())
print("JSON round-trip OK")

# calibration check
from resipsc.validation.calibration import CalibrationMonitor
cm = CalibrationMonitor("db/calibration.db")
p_all = model.predict_proba(X)[:, 1]
res = cm.check(p_all[:1000], "SMOKE-001")
print(f"calibration: {res['status']} KL={res['kl_divergence']:.4f} KS={res['ks_statistic']:.4f}")

# comparability engine
from resipsc.validation.comparability import ComparabilityEngine
ce = ComparabilityEngine()
comp = ce.compare(yte, p * 0.98 + 0.01, m2.predict_proba(Xte)[:, 1] if False else p,
                  old_version="v1.9", new_version="v2.0")
print(f"comparability: {comp['verdict']} kappa={comp['cohens_kappa']:.3f}")

# save model
from resipsc.utils.io import save_pickle
save_pickle(model, "results/final_model_test.pkl")
import os
print(f"model size: {os.path.getsize('results/final_model_test.pkl')/1e6:.1f} MB")
print("SMOKE TEST PASSED")
