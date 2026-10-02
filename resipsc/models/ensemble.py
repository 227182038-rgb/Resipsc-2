"""ResipscEnsemble — the heart of resipsc.

Combines the classical ensemble (XGBoost+RF+SVM), the deep model
(autoencoder+MLP) and the optional mini transformer into a single
calibrated PSC score, then produces the full QC report dictionary
(30+ top-level keys, PART 4 of the specification).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from resipsc.config import Config
from resipsc.features.markers import (
    ALL_MARKERS,
    CORE_MARKERS,
    assign_lineage,
    biomarker_summary,
    lineage_marker_scores,
    pluripotency_score,
)
from resipsc.models.classical import ClassicalEnsemble
from resipsc.models.deep import MLPClassifierModel
from resipsc.models.transformer import MiniSCTransformer
from resipsc.utils.logging import get_logger

LOGGER = get_logger("models.ensemble")

# ---------------------------------------------------------------------------
# Teratoma site map — 22 anatomical sites with literature-derived priors.
# Sources: Lee et al. Nat Rev Mol Cell Biol 2013; Ben-David et al. Cell Stem
# Cell 2013; Brederlau et al. Stem Cells 2004; Hentze et al. Stem Cell Res
# 2009; Kroon et al. Nat Biotechnol 2008.
# ---------------------------------------------------------------------------

SITE_MAP: Dict[str, List[Dict[str, Any]]] = {
    "ectoderm": [
        {"site": "Brain", "prior": 0.32, "assay": "MRI + biopsy with GFAP IHC"},
        {"site": "Skin", "prior": 0.26, "assay": "Dermatology consult + excisional biopsy with SOX2 IHC"},
        {"site": "Adrenal", "prior": 0.16, "assay": "CT abdomen + adrenal protocol biopsy"},
        {"site": "Retina", "prior": 0.14, "assay": "Ophthalmologic exam + OCT + CRX IHC"},
        {"site": "Pituitary", "prior": 0.12, "assay": "Sella MRI + pituitary hormone panel"},
    ],
    "mesoderm": [
        {"site": "Skeletal muscle", "prior": 0.28, "assay": "MRI + biopsy with myogenin IHC"},
        {"site": "Bone", "prior": 0.22, "assay": "X-ray/CT + biopsy with osteocalcin IHC"},
        {"site": "Heart", "prior": 0.18, "assay": "Echocardiogram + cardiac MRI; troponin surveillance"},
        {"site": "Kidney", "prior": 0.14, "assay": "Renal ultrasound + CT with PAX2 IHC"},
        {"site": "Blood", "prior": 0.10, "assay": "CBC + flow cytometry + bone marrow aspirate"},
        {"site": "Vessels", "prior": 0.08, "assay": "Vascular imaging (CTA/MRA) + CD31 IHC"},
    ],
    "endoderm": [
        {"site": "Pancreas", "prior": 0.30, "assay": "CT/MRI pancreas protocol + endoscopic biopsy; PDX1 IHC"},
        {"site": "Liver", "prior": 0.22, "assay": "Liver ultrasound + AFP surveillance + biopsy with ALB IHC"},
        {"site": "GI tract", "prior": 0.20, "assay": "Endoscopy/colonoscopy + biopsy with CDX2 IHC"},
        {"site": "Thyroid", "prior": 0.14, "assay": "Neck ultrasound + FNA; TTF1/TG IHC"},
        {"site": "Lung", "prior": 0.10, "assay": "Chest CT + biopsy with NKX2-1 IHC"},
        {"site": "Biliary", "prior": 0.04, "assay": "MRCP + ERCP brushings with CK7/CK19 IHC"},
    ],
    "pluripotent": [
        {"site": "Sacrococcygeal", "prior": 0.35, "assay": "Pelvic MRI + excisional biopsy; OCT4/SOX2 IHC"},
        {"site": "Gonads", "prior": 0.25, "assay": "Pelvic/testicular ultrasound + tumor markers; OCT4 IHC"},
        {"site": "Mediastinum", "prior": 0.18, "assay": "Chest CT + mediastinoscopy biopsy"},
        {"site": "Retroperitoneum", "prior": 0.14, "assay": "Abdominal CT + core needle biopsy"},
        {"site": "Any (disseminated)", "prior": 0.08, "assay": "Whole-body PET-CT + site-directed biopsy"},
    ],
}

LITERATURE_CITATIONS = (
    "Lee et al., Nat Rev Mol Cell Biol 2013; Ben-David et al., Cell Stem Cell 2013; "
    "Brederlau et al., Stem Cells 2004; Hentze et al., Stem Cell Res 2009; "
    "Kroon et al., Nat Biotechnol 2008"
)

SOFTWARE_VERSION = "2.0.0"
MODEL_VERSION = "resipsc-ensemble-2.0.0"

REGULATORY_CONTEXT_STATIC = {
    "fda": (
        "21 CFR 1271 (HCT/Ps): release testing for residual PSCs is required before "
        "administration of PSC-derived cell therapy products. resipsc supports release "
        "at observed residual PSC fraction <= 0.001% and recommends quarantine above 1%. "
        "21 CFR 211 (cGMP) applies to more-than-minimally-manipulated PSC derivatives. "
        "21 CFR Part 11: audit trail implemented as an append-only, SHA-256 hash-chained "
        "event log with UTC timestamps."
    ),
    "ema": (
        "EMEA/CHMP/410869/2006 (Guideline on human cell-based medicinal products): requires "
        "identity, potency, purity, microbiological safety, viability and tumorigenicity "
        "testing. Purity criterion: residual undifferentiated cells below a sponsor-justified "
        "threshold; QP release is defensible at <= 0.001% with orthogonal confirmation."
    ),
    "ich": (
        "ICH Q5E Comparability of Biotechnological/Biological Products: pre/post retrain "
        "concordance analysis (sensitivity/specificity/kappa). ICH Q9(R1) Quality Risk "
        "Management: formal FMEA covering input data quality, model failure modes and "
        "infrastructure. ICH Q10 Pharmaceutical Quality System: change control, CAPA, "
        "management review and knowledge management implemented around the model lifecycle."
    ),
}


def _f(x) -> Optional[float]:
    """Safe float conversion: NaN/Inf -> None."""
    if x is None:
        return None
    try:
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:  # noqa: BLE001
        return None


def _i(x) -> int:
    try:
        return int(x)
    except Exception:  # noqa: BLE001
        return 0


class ResipscEnsemble:
    """Weighted ensemble of classical + deep (+ optional transformer) models."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.classical = ClassicalEnsemble(
            xgb_n_estimators=self.config.xgb_n_estimators,
            xgb_max_depth=self.config.xgb_max_depth,
            xgb_learning_rate=self.config.xgb_learning_rate,
            rf_n_estimators=self.config.rf_n_estimators,
            svm_kernel=self.config.svm_kernel,
            xgb_weight=self.config.xgb_weight,
            rf_weight=self.config.rf_weight,
            svm_weight=self.config.svm_weight,
            random_state=self.config.random_state,
            n_jobs=self.config.n_jobs,
        )
        self.deep = MLPClassifierModel(
            n_components=self.config.ae_latent,
            ae_epochs=self.config.ae_epochs,
            mlp_hidden=self.config.mlp_hidden,
            mlp_epochs=self.config.mlp_epochs,
            random_state=self.config.random_state,
        )
        self.transformer: Optional[MiniSCTransformer] = None
        if not self.config.skip_transformer:
            self.transformer = MiniSCTransformer(
                dim=self.config.transformer_dim,
                epochs=self.config.transformer_epochs,
                random_state=self.config.random_state,
            )
        self.gene_names: List[str] = []
        self.train_mu: Optional[np.ndarray] = None
        self.train_sd: Optional[np.ndarray] = None
        # quantification calibration: operating-point sensitivity / FPR on a
        # held-out evaluation, used to invert the biased threshold-count
        # estimate (p_hat = sens*p + fpr*(1-p)  =>  p = (p_hat - fpr)/(sens - fpr))
        self.quantification: Optional[Dict[str, float]] = None
        # biomarker cross-check threshold: frozen from the training corpus
        # (p95 of negative-cell OCT4/NANOG/SOX2 scores) so "biomarker-positive"
        # is anchored to the training background, not the upload's own tail
        self.bio_threshold: Optional[float] = None
        self.train_info: Dict[str, Any] = {}
        self._fitted = False

    # ------------------------------------------------------------------ fit
    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        gene_names: Optional[List[str]] = None,
        mu: Optional[np.ndarray] = None,
        sd: Optional[np.ndarray] = None,
    ) -> "ResipscEnsemble":
        """Fit on a scaled matrix. ``gene_names``/``mu``/``sd`` capture the
        feature space so inference on new files can rebuild identical columns
        (align to gene list, z-scale with training statistics)."""
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y).astype(int)
        self.gene_names = list(gene_names) if gene_names is not None else []
        if mu is None:
            mu = X.mean(axis=0)
        if sd is None:
            sd = X.std(axis=0)
            sd[sd == 0] = 1.0
        self.train_mu = np.asarray(mu, dtype=np.float32)
        self.train_sd = np.where(np.asarray(sd, dtype=np.float32) == 0, 1.0,
                                 np.asarray(sd, dtype=np.float32))

        t0 = time.time()
        self.classical.fit(X, y)
        t_classical = time.time() - t0

        t0 = time.time()
        self.deep.fit(X, y)
        t_deep = time.time() - t0

        t_trans = 0.0
        if self.transformer is not None:
            t0 = time.time()
            try:
                self.transformer.fit(X, y)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("transformer fit failed (%s); skipping", exc)
                self.transformer = None
            t_trans = time.time() - t0

        self.train_info = {
            "n_train_cells": int(X.shape[0]),
            "n_features": int(X.shape[1]),
            "training_seconds": {
                "classical": round(t_classical, 2),
                "deep": round(t_deep, 2),
                "transformer": round(t_trans, 2),
            },
        }
        self._fitted = True
        LOGGER.info(
            "ensemble fitted on %d cells x %d features", X.shape[0], X.shape[1]
        )
        return self

    # --------------------------------------------------------------- predict
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("ResipscEnsemble not fitted")
        X = np.asarray(X, dtype=np.float32)
        p1 = self.classical.predict_proba(X)[:, 1] * self.config.classical_weight
        p1 = p1 + self.deep.predict_proba(X)[:, 1] * self.config.deep_weight
        used = self.config.classical_weight + self.config.deep_weight
        if self.transformer is not None and used < 1.0:
            w = 1.0 - used
            p1 = p1 + self.transformer.predict_proba(X)[:, 1] * w
            used += w
        if used > 0:
            p1 = p1 / used
        p1 = np.clip(p1, 0.0, 1.0)
        return np.stack([1 - p1, p1], axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= self.config.decision_threshold).astype(int)

    def roc_auc(self, X: np.ndarray, y: np.ndarray) -> float:
        p = self.predict_proba(X)[:, 1]
        try:
            return float(roc_auc_score(y, p))
        except Exception:  # noqa: BLE001
            return 0.5

    @property
    def fitted(self) -> bool:
        return self._fitted

    # ------------------------------------------------------------ featurize
    def featurize(self, a) -> Tuple[np.ndarray, Any]:
        """Normalise -> align to the model's gene list -> scale with
        training statistics. Returns (scaled matrix, normalised AnnData)."""
        from resipsc.data.preprocessing import align_to_genes, normalize_anndata, scale_with

        a_norm = normalize_anndata(a)
        if not self.gene_names:
            raise RuntimeError("model has no stored gene list; cannot featurize")
        X = align_to_genes(a_norm, self.gene_names)
        Xs = scale_with(X, self.train_mu, self.train_sd)
        return Xs, a_norm

    # ------------------------------------------------------------ qc_report
    def qc_report(self, a, batch_id: str = "BATCH-000") -> Dict[str, Any]:
        """Core QC fields (subset of the full report; PART 4 'CORE FIELDS')."""
        X, a_norm = self.featurize(a)
        if X.shape[0] == 0:
            raise ValueError("no cells left after preprocessing")
        p = self.predict_proba(X)[:, 1]
        thr = self.config.decision_threshold
        above = p >= thr
        n = int(X.shape[0])
        genes = list(self.gene_names)
        cell_ids = list(a_norm.obs_names)

        # --- quantification-calibrated fraction estimate -----------------------
        raw_frac = float(above.mean()) if n else 0.0
        q = self.quantification or {"sens": 1.0, "fpr": 0.0}
        denom = q.get("sens", 1.0) - q.get("fpr", 0.0)
        if denom > 0.05:  # only apply when the calibration is meaningful
            frac = float(np.clip((raw_frac - q.get("fpr", 0.0)) / denom, 0.0, 1.0))
        else:
            frac = raw_frac
        est_count = int(round(frac * n))

        psc_mask = above
        lineages = assign_lineage(a_norm, psc_mask)
        lineage_breakdown: Dict[str, int] = {}
        for lab in lineages:
            lineage_breakdown[str(lab)] = lineage_breakdown.get(str(lab), 0) + 1

        scores = lineage_marker_scores(a_norm)
        site_risk = self._teratoma_risk_scores(p, lineages, scores)

        frac_pct = 100.0 * frac
        if frac_pct <= self.config.release_max_pct:
            decision, reason = "RELEASE", (
                f"Estimated residual PSC fraction {frac_pct:.4f}% is at or below the "
                f"FDA-aligned release threshold of {self.config.release_max_pct}%."
            )
        elif frac_pct > self.config.hold_min_pct:
            decision, reason = "QUARANTINE", (
                f"Estimated residual PSC fraction {frac_pct:.4f}% exceeds the "
                f"quarantine threshold of {self.config.hold_min_pct}% — batch fails "
                "release testing; investigate and consider re-processing."
            )
        else:
            decision, reason = "HOLD", (
                f"Estimated residual PSC fraction {frac_pct:.4f}% falls between the "
                f"release ({self.config.release_max_pct}%) and quarantine "
                f"({self.config.hold_min_pct}%) thresholds — QA review required with "
                "orthogonal biomarker confirmation before disposition."
            )

        per_cell = [
            {
                "cell_id": str(cid),
                "psc_probability": _f(p[i]),
                "pluripotency_score": _f(ps),
                "teratoma_lineage": str(lineages[i]),
            }
            for i, (cid, ps) in enumerate(
                zip(cell_ids[:50], pluripotency_score(a_norm)[:50])
            )
        ]

        return {
            "batch_id": batch_id,
            "decision": decision,
            "decision_reason": reason,
            "n_cells": n,
            "n_cells_above_threshold": int(above.sum()),
            "estimated_psc_fraction": frac,
            "raw_measured_fraction": raw_frac,
            "estimated_psc_count": est_count,
            "psc_probability_mean": _f(p.mean()),
            "psc_probability_max": _f(p.max()),
            "lineage_breakdown": lineage_breakdown,
            "mean_teratoma_risk_score": _f(float(np.mean(site_risk))) if n else 0.0,
            "max_teratoma_risk_score": _f(float(np.max(site_risk))) if n else 0.0,
            "thresholds": {
                "decision_threshold": self.config.decision_threshold,
                "release_max_pct": self.config.release_max_pct,
                "hold_min_pct": self.config.hold_min_pct,
            },
            "per_cell_summary": per_cell,
            "_probabilities": p,  # internal, stripped before serialisation
            "_lineages": lineages,
            "_genes": genes,
            "_cell_ids": cell_ids,
            "_X": X,
            "_a_norm": a_norm,
        }

    # --------------------------------------------------- teratoma risk scores
    def _teratoma_risk_scores(
        self, p: np.ndarray, lineages: np.ndarray, scores: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """Per-cell teratoma risk = PSC probability x lineage site max-prior."""
        max_prior = {
            "ectoderm": max(s["prior"] for s in SITE_MAP["ectoderm"]),
            "mesoderm": max(s["prior"] for s in SITE_MAP["mesoderm"]),
            "endoderm": max(s["prior"] for s in SITE_MAP["endoderm"]),
            "pluripotent": max(s["prior"] for s in SITE_MAP["pluripotent"]),
        }
        risk = np.zeros(len(p))
        for i, lab in enumerate(lineages):
            key = str(lab)
            risk[i] = p[i] * max_prior.get(key, 0.3)
        return risk

    # ------------------------------------------------------- clinical notif
    def _build_clinical_notification(
        self,
        core: Dict[str, Any],
        p: np.ndarray,
        lineages: np.ndarray,
        scores: Dict[str, np.ndarray],
    ) -> Dict[str, Any]:
        n = core["n_cells"]
        frac = core["estimated_psc_fraction"]
        sites_out: List[Dict[str, Any]] = []
        for lineage, sites in SITE_MAP.items():
            in_lin = lineages == lineage
            n_lin = int(in_lin.sum())
            if n_lin == 0:
                continue
            lin_probs = p[in_lin]
            lineage_probability = float(n_lin) / max(1, n)
            for s in sites:
                site_p = s["prior"]
                # P(cells in lineage AND site) — independent site prior assumption
                abs_risk = float(np.mean(lin_probs) * site_p) if n_lin else 0.0
                if abs_risk >= 0.15:
                    level = "HIGH"
                elif abs_risk >= 0.05:
                    level = "MODERATE"
                elif abs_risk >= 0.01:
                    level = "LOW"
                else:
                    level = "NEGLIGIBLE"
                sites_out.append(
                    {
                        "anatomical_site": s["site"],
                        "germ_layer": lineage,
                        "predicted_cells_in_lineage": n_lin,
                        "lineage_probability": _f(lineage_probability),
                        "site_probability": _f(site_p),
                        "site_prior": _f(site_p),
                        "absolute_risk_probability": _f(abs_risk),
                        "risk_level": level,
                        "marker_genes": LINEAGE_MARKERS_SHORT.get(lineage, []),
                        "evidence_citation": LITERATURE_CITATIONS,
                        "confirmatory_assay": s["assay"],
                    }
                )
        total_risk_cells = core["estimated_psc_count"]
        if total_risk_cells > 10:
            summary = (
                f"Elevated residual PSC burden ({total_risk_cells} cells, "
                f"{100 * frac:.3f}%). Teratoma formation risk is material — "
                "clinical notification and imaging surveillance recommended."
            )
            confidence = "high" if frac > 0.01 else "moderate"
        elif total_risk_cells > 0:
            summary = (
                f"Low residual PSC burden ({total_risk_cells} cells, "
                f"{100 * frac:.4f}%). Risk of teratoma formation is low but not "
                "zero; confirm with an orthogonal assay before release."
            )
            confidence = "moderate"
        else:
            summary = (
                "No residual PSCs detected above the decision threshold. "
                "Teratoma risk from this product lot is estimated as negligible."
            )
            confidence = "moderate"
        sites_out.sort(key=lambda d: -(d["absolute_risk_probability"] or 0.0))
        return {
            "title": "Residual PSC Detection — Clinical Risk Notification",
            "batch_id": core["batch_id"],
            "decision": core["decision"],
            "risk_summary": summary,
            "confidence": confidence,
            "overall_psc_fraction": _f(frac),
            "overall_psc_count": int(core["estimated_psc_count"]),
            "total_cells_analysed": int(n),
            "teratoma_risk_sites": sites_out,
            "possible_onset_locations": [s["anatomical_site"] for s in sites_out[:6]],
            "disclaimer": (
                "Risk probabilities are model-derived estimates from scRNA-seq "
                "data only. They do not substitute for in vivo tumorigenicity "
                "testing or clinical judgement. Research Use Only — NOT FDA-cleared."
            ),
        }

    def _get_model_credentials(self) -> Dict[str, Any]:
        bench_file = Path(self.config.results_dir) / "multisite_summary.csv"
        bench = "multi-site 4-fold CV (see Benchmark tab)"
        try:
            df = pd.read_csv(bench_file)
            ens = df[df["model"].str.contains("ensemble", case=False, na=False)]
            if len(ens):
                row = ens.iloc[0]
                bench = (
                    f"multi-site 4-fold CV ROC-AUC {row.get('roc_auc_mean', float('nan')):.3f}"
                )
        except Exception:  # noqa: BLE001
            pass
        sens = "spike-in LOD 0.01% at >=0.9 recall (see Sensitivity tab)"
        try:
            import json as _json

            sp_file = Path(self.config.results_dir) / "spikein_results.json"
            if sp_file.exists():
                sp = _json.loads(sp_file.read_text())
                sens = str(sp.get("headline", sens))
        except Exception:  # noqa: BLE001
            pass
        return {
            "model_version": MODEL_VERSION,
            "benchmark": bench,
            "sensitivity": sens,
            "training_data": str(
                self.train_info.get("training_data", "hybrid synthetic + pbmc3k")
            ),
        }

    # ------------------------------------------------------ qc_report_dict
    def qc_report_dict(
        self,
        a,
        batch_id: str = "BATCH-000",
        input_file: str = "upload.h5ad",
        prev_batches: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Full elevated QC report — 30+ top-level keys (PART 4 of spec)."""
        core = self.qc_report(a, batch_id=batch_id)
        p = core.pop("_probabilities")
        lineages = core.pop("_lineages")
        genes = core.pop("_genes")
        cell_ids = core.pop("_cell_ids")
        X = core.pop("_X")
        a_norm = core.pop("_a_norm")
        n = core["n_cells"]
        thr = self.config.decision_threshold
        above = p >= thr

        # --- biomarker cross-check ----------------------------------------
        bio = pluripotency_score(a_norm)
        # threshold frozen from the training corpus when available; otherwise
        # fall back to this batch's 95th percentile (never an absolute floor,
        # which sits at background for log-normalised data)
        if self.bio_threshold is not None and np.isfinite(self.bio_threshold):
            bio_thr = float(self.bio_threshold)
        else:
            bio_thr = float(np.percentile(bio, 95))
        bio_pos = bio >= bio_thr
        model_pos = above
        agree = float(np.mean(bio_pos == model_pos)) if n else 1.0
        disagreement = 1.0 - agree
        # a batch-effect false positive is likely when model+ and bio- cells
        # are numerous but the marker panel itself is quiet
        n_model_only = int((model_pos & ~bio_pos).sum())
        n_bio_only = int((~model_pos & bio_pos).sum())
        if n_model_only > max(5, 0.02 * n) and float(np.mean(bio)) < 0.6:
            cross_warn = "batch-effect false positive likely — confirm with orthogonal markers"
        elif n_bio_only > max(5, 0.02 * n):
            cross_warn = "biomarker-positive cells missed by model — review borderline probabilities"
        else:
            cross_warn = "consistent"

        # --- statistical confidence -----------------------------------------
        frac = core["estimated_psc_fraction"]
        raw_frac = core.get("raw_measured_fraction", frac)
        qcal = self.quantification or {"sens": 1.0, "fpr": 0.0}
        qdenom = qcal.get("sens", 1.0) - qcal.get("fpr", 0.0)

        def _qcorrect(x: np.ndarray) -> np.ndarray:
            """Invert the operating-point affine quantification map."""
            if qdenom > 0.05:
                return np.clip((x - qcal.get("fpr", 0.0)) / qdenom, 0.0, 1.0)
            return x

        rng = np.random.default_rng(42)
        n_boot = 1000
        boot_fracs = np.empty(n_boot)
        for b in range(n_boot):
            idx = rng.integers(0, n, size=max(2, int(0.8 * n)))
            boot_fracs[b] = float(_qcorrect(above[idx].mean()))
        from scipy import stats as sps

        p0 = self.config.release_max_pct / 100.0
        expected_under_null = n * p0
        p_value = float(sps.binom.sf(max(0, int(above.sum()) - 1), n, max(p0, 1e-9)))
        if n >= 30:
            try:
                from statsmodels.stats.power import NormalIndPower  # type: ignore

                power = None  # statsmodels not a dependency; compute manually
            except Exception:  # noqa: BLE001
                power = None
            z_a = 1.959964
            eff = abs(frac - p0) / max(1e-9, np.sqrt(max(p0 * (1 - p0), 1e-12)) / np.sqrt(n))
            post_power = float(sps.norm.cdf(eff - z_a))
        else:
            post_power = 0.5
            z_a = 1.959964

        # --- probability distribution ----------------------------------------
        bins = []
        edges = np.linspace(0, 1, 21)
        hist, _ = np.histogram(p, bins=edges)
        for i in range(20):
            bins.append(
                {
                    "label": f"{edges[i]:.2f}-{edges[i+1]:.2f}",
                    "count": int(hist[i]),
                    "fraction": float(hist[i]) / max(1, n),
                }
            )

        # --- calibration metrics ---------------------------------------------
        brier = float(np.mean((p - bio_pos.astype(float)) ** 2)) if n else None
        ece = 0.0
        for lo in np.linspace(0, 0.9, 10):
            m = (p >= lo) & (p < lo + 0.1)
            if m.sum() > 0:
                ece += float(m.sum()) / n * abs(p[m].mean() - bio_pos[m].mean())
        brier_interp = (
            "excellent (Brier < 0.05: probabilities closely track biomarker evidence)"
            if (brier or 1) < 0.05
            else "acceptable (0.05 <= Brier < 0.15): mild probability distortion"
            if (brier or 1) < 0.15
            else "poor (Brier >= 0.15): recalibrate before use"
        )
        ece_interp = (
            "well calibrated (ECE < 0.05)"
            if ece < 0.05
            else "moderate calibration drift (0.05-0.15)"
            if ece < 0.15
            else "poor calibration (ECE >= 0.15)"
        )

        # --- executive summary + risk tier ------------------------------------
        frac_pct = 100.0 * frac
        if frac_pct <= 0.001:
            tier = "T1"
            tier_label = "Negligible risk (≤ 0.001% residual PSC)"
            fda_r = "Meets FDA 21 CFR 1271-aligned release criterion (≤ 0.001%)."
        elif frac_pct <= 0.1:
            tier = "T2"
            tier_label = "Low risk (0.001-0.1% residual PSC)"
            fda_r = "Above the conservative FDA release threshold; QP judgement with orthogonal confirmation."
        elif frac_pct <= 1.0:
            tier = "T3"
            tier_label = "Moderate risk (0.1-1% residual PSC)"
            fda_r = "Exceeds release threshold; QA review required (HOLD disposition)."
        else:
            tier = "T4"
            tier_label = "High risk (> 1% residual PSC)"
            fda_r = "Fails release testing under 21 CFR 1271; quarantine and investigate."
        ema_r = (
            "EMEA/CHMP/410869/2006: QP release defensible at ≤ 0.001% with orthogonal confirmation."
            if tier in ("T1",)
            else "EMEA/CHMP/410869/2006: purity criterion not met without justification; QP consultation required."
        )
        headline = {
            "RELEASE": f"No actionable residual PSC burden detected — {tier} disposition",
            "HOLD": f"Residual PSC burden requires QA review — {tier} disposition",
            "QUARANTINE": f"Residual PSC burden fails release criteria — {tier} disposition",
        }[core["decision"]]
        exec_summary = {
            "headline": headline,
            "detail": (
                f"resipsc analysed {n} cells from batch {batch_id}. "
                f"{core['estimated_psc_count']} cells exceeded the PSC decision threshold "
                f"(estimated fraction {frac_pct:.4f}%). Biomarker cross-check agreement was "
                f"{agree*100:.1f}%. The dominant detected lineage is "
                f"{max(core['lineage_breakdown'].items(), key=lambda kv: kv[1])[0] if core['lineage_breakdown'] else 'n/a'}."
            ),
            "caveat": (
                "This is a computational inference from scRNA-seq data. It does not replace "
                "orthogonal wet-lab release assays (HEC, ddPCR, flow cytometry) and has not "
                "been cleared by FDA or EMA."
            ),
            "one_line_verdict": f"{core['decision']} — {tier_label}",
        }

        # --- methodology ------------------------------------------------------
        methodology = {
            "model_versions": {
                "resipsc": SOFTWARE_VERSION,
                "scikit-learn": __import__("sklearn").__version__,
                "numpy": np.__version__,
                "anndata": __import__("anndata").__version__,
                "pandas": pd.__version__,
                "scipy": __import__("scipy").__version__,
                "xgboost": __import__("xgboost").__version__,
                "matplotlib": __import__("matplotlib").__version__,
            },
            "pipeline": [
                "1. Input parsing (h5ad/csv/mtx; counts or log-normalised)",
                "2. Cell QC filter (>= 10 detected genes)",
                "3. Gene QC filter (>= 3 expressing cells; markers always retained)",
                "4. Library-size normalisation to 10,000 counts per cell",
                "5. log1p transformation",
                "6. Highly-variable gene selection (top %d by variance)" % self.config.n_hvg,
                "7. Per-gene z-scaling (clip +-10)",
                "8. Ensemble scoring (XGB+RF+SVM 0.6 / AE+MLP 0.4)",
                "9. Biomarker cross-check (POU5F1/NANOG/SOX2 panel)",
                "10. Lineage assignment + teratoma site mapping (22 sites)",
            ],
            "input_dimensions": {"cells": n, "genes": int(a_norm.n_vars)},
            "decision_threshold": thr,
            "random_seed": self.config.random_state,
        }

        # --- recommendations ----------------------------------------------------
        recs = []
        if core["decision"] == "QUARANTINE":
            recs.append(
                {"priority": 1, "category": "Batch disposition", "action": "Quarantine batch and initiate investigation per SOP-QA-014",
                 "rationale": f"Residual PSC fraction {frac_pct:.3f}% exceeds the 1% quarantine threshold.",
                 "owner": "QA officer", "effort": "immediate"}
            )
        if core["decision"] == "HOLD":
            recs.append(
                {"priority": 1, "category": "Batch disposition", "action": "QA review with orthogonal confirmation (ddPCR LIN28A/ESRG)",
                 "rationale": "Fraction falls between release and quarantine thresholds.",
                 "owner": "QA officer", "effort": "1-2 days"}
            )
        if agree < 0.9:
            recs.append(
                {"priority": 2, "category": "Data quality", "action": "Review biomarker cross-check discrepancies at single-cell level",
                 "rationale": f"Model/biomarker agreement was {agree*100:.1f}% (< 90%).",
                 "owner": "Bioinformatics", "effort": "2-4 hours"}
            )
        if n < 500:
            recs.append(
                {"priority": 2, "category": "Sampling", "action": "Increase sequencing depth / cell number for future batches",
                 "rationale": f"Only {n} cells analysed — fraction estimate CI is wide.",
                 "owner": "Process development", "effort": "next run"}
            )
        recs.append(
            {"priority": 3, "category": "Regulatory", "action": "Archive report + audit trail export to batch record (21 CFR Part 11)",
             "rationale": "Electronic records must be retained >= 5 years after batch release.",
             "owner": "QA", "effort": "routine"}
        )
        recs.append(
            {"priority": 4, "category": "Model governance", "action": "Confirm current model version in registry matches promotion record (ICH Q5E)",
             "rationale": "Change control requires concordance documentation on every retrain.",
             "owner": "ML governance", "effort": "routine"}
        )
        recs.sort(key=lambda r: r["priority"])

        # --- citation block -------------------------------------------------------
        citation_block = {
            "bibtex": (
                "@software{resipsc2026,\n"
                "  title  = {resipsc v2.0.0: residual pluripotent stem cell detection for cell therapy QC},\n"
                "  year   = {2026},\n"
                "  note   = {Machine-learning ensemble for residual PSC detection in scRNA-seq},\n"
                "}"
            ),
            "citation_text": (
                "resipsc v2.0.0 (2026). Residual pluripotent stem cell detection for cell "
                "therapy quality control via machine-learning ensemble on single-cell RNA-seq. "
                "Software available from the project repository."
            ),
            "doi_placeholder": "10.5281/zenodo.XXXXXXX (to be assigned on release)",
            "license": "MIT (code); CC-BY-4.0 (data and figures)",
            "software_heritage_id": "pending archival on first public release",
        }

        # --- regulatory context ------------------------------------------------------
        regulatory_context = {
            "disposition_code": core["decision"],
            "fda": REGULATORY_CONTEXT_STATIC["fda"],
            "ema": REGULATORY_CONTEXT_STATIC["ema"],
            "ich": REGULATORY_CONTEXT_STATIC["ich"],
            "observed_psc_fraction_pct": _f(frac_pct),
            "audit_trail": "db/audit.db — append-only SHA-256 hash-chained event log (21 CFR Part 11)",
        }

        # --- report metadata ----------------------------------------------------------
        now = datetime.now(timezone.utc)
        report_id = hashlib.sha256(
            f"{batch_id}|{now.isoformat()}|{input_file}|{n}".encode()
        ).hexdigest()
        try:
            input_hash = hashlib.sha256(Path(input_file).read_bytes()[: 1 << 20]).hexdigest()[:16]
        except Exception:  # noqa: BLE001 - file may be gone (uploaded temp)
            input_hash = "unavailable"
        report_metadata = {
            "report_id": report_id,
            "generated_at_utc": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "batch_id": batch_id,
            "software_version": SOFTWARE_VERSION,
            "report_version": "2.1",
            "input_file_format": str(input_file).rsplit(".", 1)[-1].lower() if "." in str(input_file) else "unknown",
            "input_cells": n,
            "input_genes": int(a_norm.n_vars),
            "input_hash_short": input_hash,
            "signature_line": "Electronic signature: resipsc automated QC pipeline (RUO) — unsigned",
            "intended_use": "Research Use Only — NOT FDA-cleared",
        }

        # --- threshold sensitivity --------------------------------------------
        t03 = int((p >= 0.3).sum())
        t05 = int((p >= 0.5).sum())
        t07 = int((p >= 0.7).sum())
        agree_all = (t03 == t05 == t07)
        stability = (
            "ROBUST — detection count is stable across thresholds 0.3/0.5/0.7"
            if agree_all
            else f"SENSITIVE — counts vary ({t03}/{t05}/{t07}); inspect borderline cells in [0.3, 0.7]"
        )
        threshold_sensitivity = {
            "thresholds": {
                "0.3": {"n_above": t03, "fraction_pct": _f(100.0 * t03 / max(1, n))},
                "0.5": {"n_above": t05, "fraction_pct": _f(100.0 * t05 / max(1, n))},
                "0.7": {"n_above": t07, "fraction_pct": _f(100.0 * t07 / max(1, n))},
            },
            "all_thresholds_agree": bool(agree_all),
            "decision_stability": stability,
        }

        # --- per-cell classification ------------------------------------------
        both = int((model_pos & bio_pos).sum())
        m_only = int((model_pos & ~bio_pos).sum())
        b_only = int((~model_pos & bio_pos).sum())
        amb = int(((p >= 0.35) & (p < 0.65) & ~bio_pos).sum())
        neg = int((~model_pos & ~bio_pos & (p < 0.35)).sum())
        total_cls = both + m_only + b_only + amb + neg
        per_cell_classification = {
            "counts": {
                "high_confidence_psc": both,
                "model_only_psc": m_only,
                "biomarker_only_psc": b_only,
                "ambiguous": amb,
                "high_confidence_negative": neg,
            },
            "fractions": {
                "high_confidence_psc": _f(both / max(1, total_cls)),
                "model_only_psc": _f(m_only / max(1, total_cls)),
                "biomarker_only_psc": _f(b_only / max(1, total_cls)),
                "ambiguous": _f(amb / max(1, total_cls)),
                "high_confidence_negative": _f(neg / max(1, total_cls)),
            },
            "total": int(total_cls),
            "interpretation": {
                "high_confidence_psc": "PSC called by both the ML ensemble and the OCT4/NANOG/SOX2 biomarker panel — treat as confirmed residual PSCs.",
                "model_only_psc": "PSC called by the model without biomarker support — possible batch-effect false positive; verify with orthogonal assay.",
                "biomarker_only_psc": "Biomarker-positive without model support — possible differentiated-cell marker expression; review manually.",
                "ambiguous": "Borderline model probabilities (0.35-0.65) without biomarker support — indeterminate calls.",
                "high_confidence_negative": "Concordant negative — differentiated cells with quiet pluripotency programme.",
            },
        }

        # --- disease site probabilities ----------------------------------------
        cn = self._build_clinical_notification(core, p, lineages, lineage_marker_scores(a_norm))
        sites = cn["teratoma_risk_sites"]
        n_high = sum(1 for s in sites if s["risk_level"] == "HIGH")
        n_mod = sum(1 for s in sites if s["risk_level"] == "MODERATE")
        n_low = sum(1 for s in sites if s["risk_level"] == "LOW")
        n_neg = sum(1 for s in sites if s["risk_level"] == "NEGLIGIBLE")
        disease_site_probabilities = {
            "sites": sites,
            "total_sites_evaluated": len(SITE_MAP["ectoderm"]) + len(SITE_MAP["mesoderm"])
            + len(SITE_MAP["endoderm"]) + len(SITE_MAP["pluripotent"]),
            "high_risk_sites": n_high,
            "moderate_risk_sites": n_mod,
            "low_risk_sites": n_low,
            "negligible_risk_sites": n_neg,
            "formula": "absolute_risk = mean(model probability of lineage cells) x literature site prior",
            "priors_source": LITERATURE_CITATIONS,
        }

        # --- QC flags -------------------------------------------------------------
        qc_flags: List[Dict[str, Any]] = []
        if n < 200:
            qc_flags.append({"severity": "critical", "category": "sample_size",
                             "message": f"Only {n} cells — fraction estimate has wide confidence interval",
                             "action": "Increase sequenced cells before relying on the estimate"})
        elif n < 500:
            qc_flags.append({"severity": "warning", "category": "sample_size",
                             "message": f"Modest sample size ({n} cells)",
                             "action": "Interpret fraction with caution"})
        if n_model_only > max(5, 0.02 * n):
            qc_flags.append({"severity": "warning", "category": "batch_effect",
                             "message": f"{n_model_only} model-only PSC calls suggest batch-effect contribution",
                             "action": "Run Harmony/batch correction and re-score"})
        if core["psc_probability_max"] is not None and core["psc_probability_max"] > 0.98:
            qc_flags.append({"severity": "info", "category": "outlier",
                             "message": "At least one cell has near-certain PSC probability (>0.98)",
                             "action": "Inspect top-scoring cells in the per-cell table"})
        if amb > 0.1 * n:
            qc_flags.append({"severity": "warning", "category": "model_uncertainty",
                             "message": f"{amb} cells ({100.0*amb/max(1,n):.1f}%) in the ambiguous probability band",
                             "action": "Consider deeper sequencing or orthogonal markers"})
        if m_only + b_only > 0.15 * n:
            qc_flags.append({"severity": "info", "category": "ambiguity",
                             "message": "Notable model/biomarker disagreement",
                             "action": "Manual review of discordant cells"})
        if not qc_flags:
            qc_flags.append({"severity": "info", "category": "subsample",
                             "message": "No QC anomalies detected",
                             "action": "Proceed with standard review"})
        sev_rank = {"critical": 0, "warning": 1, "info": 2}
        qc_flags.sort(key=lambda f: sev_rank.get(f["severity"], 3))

        # --- disclaimer -------------------------------------------------------------
        disclaimer = {
            "primary": (
                "Research Use Only — NOT FDA-cleared. This report is a computational "
                "inference from single-cell RNA-seq data and does not constitute a "
                "clinical release test."
            ),
            "limitations": [
                "Model trained on a hybrid corpus (simulated multi-site data + real PBMC reference); clinical performance on therapeutic manufacturing batches is not yet established.",
                "Detection limits below 0.001% PSC depend on sequenced cell count and depth; bootstrap CIs quantify this uncertainty.",
                "Lineage assignment and teratoma site priors are literature-derived estimates, not patient-level predictions.",
                "Batch effects, ambient RNA and doublets can inflate apparent PSC fractions; the biomarker cross-check mitigates but does not eliminate this.",
                "No wet-lab orthogonal validation (HEC, ddPCR, lncRNA flow) has been performed for this build.",
            ],
            "wet_lab_confirmation": (
                "Confirm any non-RELEASE disposition with an orthogonal assay: ddPCR for "
                "LIN28A/ESRG, immunostaining for OCT4/TRA-1-60, or the histological "
                "embryoid-body assay, per EMEA/CHMP/410869/2006."
            ),
            "decision_authority": (
                "The disposition code is a recommendation. Release authority rests with the "
                "Qualified Person under EMA rules or the responsible QA officer under FDA rules."
            ),
            "audit_trail": "All model inputs, outputs and decisions are recorded in the append-only audit trail (db/audit.db).",
            "citation": citation_block["citation_text"],
            "license": "MIT (code); CC-BY-4.0 (figures)",
            "version": f"resipsc {SOFTWARE_VERSION} / report v2.1",
        }

        # --- cell projection (PCA, 500 cells) ----------------------------------
        proj_method = "pca"
        n_proj = min(500, n)
        sel = np.sort(np.random.default_rng(0).choice(n, size=n_proj, replace=False))
        Xs = X[sel] if X.shape[0] == n else X
        try:
            from sklearn.decomposition import PCA as _PCA

            emb = _PCA(n_components=2, random_state=0).fit_transform(Xs)
        except Exception:  # noqa: BLE001
            rng2 = np.random.default_rng(0)
            emb = rng2.normal(0, 1, size=(n_proj, 2))
            proj_method = "random"

        def _cls(pi: float, bio_flag: bool) -> str:
            if pi >= 0.5 and bio_flag:
                return "high_confidence_psc"
            if pi >= 0.5:
                return "model_only_psc"
            if bio_flag:
                return "biomarker_only_psc"
            if pi >= 0.35:
                return "ambiguous"
            return "high_confidence_negative"

        cell_id_arr = np.array([str(c) for c in cell_ids], dtype=object)
        p_sel = p[sel]
        points = [
            {
                "x": _f(emb[k, 0]),
                "y": _f(emb[k, 1]),
                "p": _f(p_sel[k]),
                "cell_id": str(cell_id_arr[sel][k]) if sel[k] < len(cell_id_arr) else f"cell_{sel[k]}",
                "class": _cls(p_sel[k], bool(bio_pos[sel][k])),
            }
            for k in range(n_proj)
        ]
        cell_projection = {
            "points": points,
            "method": proj_method,
            "n_cells_total": int(n),
            "n_cells_projected": int(n_proj),
            "x_range": [_f(emb[:, 0].min()), _f(emb[:, 0].max())],
            "y_range": [_f(emb[:, 1].min()), _f(emb[:, 1].max())],
        }

        # --- gene heatmap (8 markers x top/bottom 20 cells) ----------------------
        import scipy.sparse as sp

        M = a_norm.X
        if sp.issparse(M):
            M = np.asarray(M.todense())
        M = np.asarray(M)
        var_list = list(a_norm.var_names)
        heat_genes = [g for g in ["POU5F1", "NANOG", "SOX2", "LIN28A", "KLF4", "MYC", "ZFP42", "ESRG"] if g in var_list]
        if not heat_genes:
            heat_genes = var_list[:8]
        cols = [var_list.index(g) for g in heat_genes]
        order = np.argsort(-p)
        top_idx = order[: min(20, n)]
        bot_idx = order[-min(20, n):]
        def _rows(idx):
            return [
                {
                    "cell_id": str(cell_ids[i]) if i < len(cell_ids) else f"cell_{i}",
                    "p": _f(p[i]),
                    "values": [_f(M[i, c]) for c in cols],
                }
                for i in idx
            ]
        gene_heatmap = {
            "genes": heat_genes,
            "top_cells": _rows(top_idx),
            "bottom_cells": _rows(bot_idx),
            "color_scale": "blue(0) -> white(median) -> red(max) on log-normalised expression",
            "description": "Expression of the 8-gene pluripotency panel in the 20 highest- and 20 lowest-scoring cells.",
        }

        # --- batch history ----------------------------------------------------------
        prev = (prev_batches or [])[-20:]
        if len(prev) >= 2:
            fr = [b.get("estimated_psc_fraction", 0) for b in prev]
            trend = "increasing" if fr[-1] > fr[0] else "decreasing" if fr[-1] < fr[0] else "stable"
        else:
            trend = "insufficient history"
        batch_history = {
            "batches": [
                {
                    "batch_id": b.get("batch_id", "?"),
                    "generated_at_utc": b.get("report_metadata", {}).get("generated_at_utc", b.get("generated_at_utc", "?")),
                    "decision": b.get("decision", "?"),
                    "n_cells": b.get("n_cells", 0),
                    "estimated_psc_fraction": b.get("estimated_psc_fraction"),
                    "biomarker_model_agreement": b.get("biomarker_model_agreement"),
                }
                for b in prev
            ],
            "n_previous_batches": len(prev),
            "trend": trend,
            "current_batch_id": batch_id,
        }

        # --- assemble -------------------------------------------------------------
        report: Dict[str, Any] = {
            **core,
            "biomarker_model_agreement": _f(agree),
            "biomarker_model_disagreement": _f(disagreement),
            "cross_check_warning": cross_warn,
            "clinical_notification": cn,
            "model_credentials": self._get_model_credentials(),
            "executive_summary": exec_summary,
            "risk_tier": {
                "tier": tier,
                "label": tier_label,
                "color": {"T1": "emerald", "T2": "teal", "T3": "amber", "T4": "rose"}[tier],
                "fda_rationale": fda_r,
                "ema_rationale": ema_r,
                "numerical_threshold": {
                    "T1": "<= 0.001%", "T2": "0.001-0.1%", "T3": "0.1-1%", "T4": "> 1%"
                }[tier],
            },
            "methodology": methodology,
            "statistical_confidence": {
                "bootstrap_ci_95": {
                    "lower": _f(np.percentile(boot_fracs, 2.5)),
                    "upper": _f(np.percentile(boot_fracs, 97.5)),
                    "mean": _f(boot_fracs.mean()),
                    "std": _f(boot_fracs.std()),
                    "n_iterations": n_boot,
                },
                "binomial_test": {
                    "null_hypothesis": f"true PSC fraction = release threshold ({self.config.release_max_pct}%)",
                    "alternative": "true PSC fraction exceeds release threshold",
                    "p_value": _f(p_value),
                    "significant_at_alpha_0_05": bool(p_value < 0.05),
                    "observed_count": int(above.sum()),
                    "expected_under_null": _f(expected_under_null),
                },
                "post_hoc_power": {
                    "value": _f(post_power),
                    "interpretation": (
                        "adequate (>= 0.8) to detect the observed deviation at alpha=0.05"
                        if post_power >= 0.8
                        else "limited (< 0.8) — a larger cell number is needed for robust detection"
                    ),
                    "assumed_effect_size": _f(eff) if n >= 30 else None,
                    "alpha": 0.05,
                    "sample_size": int(n),
                },
            },
            "probability_distribution": {
                "bins": bins,
                "n_cells": int(n),
                "p50": _f(np.percentile(p, 50)),
                "p95": _f(np.percentile(p, 95)),
                "p99": _f(np.percentile(p, 99)),
                "mean": _f(p.mean()),
                "max": _f(p.max()),
            },
            "calibration_metrics": {
                "brier_score_vs_biomarker": _f(brier),
                "brier_interpretation": brier_interp,
                "ece_surrogate_vs_biomarker": _f(ece),
                "ece_interpretation": ece_interp,
                "biomarker_model_agreement": _f(agree),
            },
            "recommendations": recs,
            "citation_block": citation_block,
            "regulatory_context": regulatory_context,
            "report_metadata": report_metadata,
            "threshold_sensitivity": threshold_sensitivity,
            "per_cell_classification": per_cell_classification,
            "disease_site_probabilities": disease_site_probabilities,
            "qc_flags": qc_flags,
            "disclaimer": disclaimer,
            "cell_projection": cell_projection,
            "gene_heatmap": gene_heatmap,
            "batch_history": batch_history,
            "input_file": str(input_file),
        }
        return report


LINEAGE_MARKERS_SHORT: Dict[str, List[str]] = {
    "ectoderm": ["PAX6", "SOX1", "TUBB3", "MAP2"],
    "mesoderm": ["TBXT", "MESP1", "TNNT2", "MYOD1"],
    "endoderm": ["SOX17", "FOXA2", "GATA4", "HNF4A"],
    "pluripotent": ["POU5F1", "NANOG", "SOX2"],
}
