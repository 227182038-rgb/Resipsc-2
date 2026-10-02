"""Classical ensemble: XGBoost + RandomForest + SVM with calibration.

The three base learners are combined via a fixed weighted average
(xgb 0.5 / rf 0.25 / svm 0.25 by default) of calibrated probabilities.

SVM note (PART 3.7): sklearn >= 1.9 deprecates SVC(probability=True).
We therefore wrap a plain SVC inside CalibratedClassifierCV(sigmoid) with a
StratifiedKFold; if calibration itself fails we fall back to a Platt-sigmoid
transform of decision_function — silently, without warnings.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from resipsc.utils.logging import get_logger

LOGGER = get_logger("models.classical")

try:  # xgboost is optional at import time (numpy ABI differences)
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:  # noqa: BLE001
    HAS_XGB = False
    LOGGER.warning("xgboost unavailable; ensemble will up-weight RF")


class ClassicalEnsemble:
    """Weighted XGBoost + RandomForest + SVM classifier."""

    def __init__(
        self,
        xgb_n_estimators: int = 80,
        xgb_max_depth: int = 4,
        xgb_learning_rate: float = 0.1,
        rf_n_estimators: int = 80,
        svm_kernel: str = "linear",
        xgb_weight: float = 0.5,
        rf_weight: float = 0.25,
        svm_weight: float = 0.25,
        random_state: int = 42,
        n_jobs: int = 1,
    ) -> None:
        self.params = dict(
            xgb_n_estimators=xgb_n_estimators,
            xgb_max_depth=xgb_max_depth,
            xgb_learning_rate=xgb_learning_rate,
            rf_n_estimators=rf_n_estimators,
            svm_kernel=svm_kernel,
        )
        self.weights = {"xgb": xgb_weight, "rf": rf_weight, "svm": svm_weight}
        self.random_state = random_state
        self.n_jobs = n_jobs

        self.scaler = StandardScaler()
        self.xgb = None
        self.rf = None
        self.svm = None
        self._svm_raw = None  # uncalibrated fallback
        self._svm_platt: Optional[Tuple[float, float]] = None
        self.classes_ = np.array([0, 1])
        self._fitted = False

    # ------------------------------------------------------------------
    def _make_svm(self) -> SVC:
        return SVC(kernel=self.params["svm_kernel"], C=1.0, gamma="scale",
                   random_state=self.random_state)

    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "ClassicalEnsemble":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y).astype(int)
        self.classes_ = np.unique(y)

        Xs = self.scaler.fit_transform(X)

        # --- XGBoost -----------------------------------------------------
        if HAS_XGB:
            self.xgb = XGBClassifier(
                n_estimators=self.params["xgb_n_estimators"],
                max_depth=self.params["xgb_max_depth"],
                learning_rate=self.params["xgb_learning_rate"],
                subsample=0.9,
                colsample_bytree=0.8,
                eval_metric="logloss",
                random_state=self.random_state,
                n_jobs=self.n_jobs,
                tree_method="hist",
                verbosity=0,
            )
            try:
                self.xgb.fit(X, y)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("XGB fit failed (%s); dropping XGB", exc)
                self.xgb = None
                self.weights["rf"] += self.weights["xgb"]
                self.weights["xgb"] = 0.0
        else:
            self.weights["rf"] += self.weights["xgb"]
            self.weights["xgb"] = 0.0

        # --- RandomForest --------------------------------------------------
        self.rf = RandomForestClassifier(
            n_estimators=self.params["rf_n_estimators"],
            max_depth=8,
            min_samples_leaf=2,
            random_state=self.random_state,
            n_jobs=self.n_jobs,
            class_weight="balanced_subsample",
        )
        self.rf.fit(X, y)

        # --- SVM with calibration (PART 3.7) ---------------------------------
        raw = self._make_svm()
        try:
            n_splits = int(min(3, np.bincount(y).min()))
            if n_splits >= 2:
                cv = StratifiedKFold(n_splits=n_splits, shuffle=True,
                                     random_state=self.random_state)
                self.svm = CalibratedClassifierCV(raw, method="sigmoid", cv=cv)
                self.svm.fit(Xs, y)
            else:
                raise ValueError("too few samples per class for CV")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("SVM calibration failed (%s); Platt fallback", exc)
            self.svm = None
            self._svm_raw = raw.fit(Xs, y)
            d = self._svm_raw.decision_function(Xs)
            if len(np.unique(y)) == 2:
                p = 1.0 / (1.0 + np.exp(-d))
                eps = 1e-6
                mu = np.log(np.clip(p[y == 1], eps, 1 - eps).mean() /
                           np.clip(p[y == 0], eps, 1 - eps).mean())
                self._svm_platt = (float(mu), 1.0)

        self._fitted = True
        return self

    # ------------------------------------------------------------------
    def _svm_proba(self, Xs: np.ndarray) -> np.ndarray:
        n = Xs.shape[0]
        if self.svm is not None:
            try:
                return self.svm.predict_proba(Xs)[:, 1]
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("SVM predict_proba failed (%s); Platt", exc)
        if self._svm_raw is not None:
            d = self._svm_raw.decision_function(Xs)
            p = 1.0 / (1.0 + np.exp(-d))
            if self._svm_platt is not None:
                mu, a = self._svm_platt
                p = 1.0 / (1.0 + np.exp(-(a * np.log(np.clip(p, 1e-9, None)) + mu)))
            return p
        return np.full(n, 0.5)

    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return (n, 2) probability matrix for the weighted ensemble."""
        if not self._fitted:
            raise RuntimeError("ClassicalEnsemble not fitted")
        X = np.asarray(X, dtype=np.float32)
        Xs = self.scaler.transform(X)

        parts = []
        wsum = 0.0
        if self.xgb is not None and self.weights["xgb"] > 0:
            parts.append(self.weights["xgb"] * self.xgb.predict_proba(X)[:, 1])
            wsum += self.weights["xgb"]
        if self.rf is not None and self.weights["rf"] > 0:
            parts.append(self.weights["rf"] * self.rf.predict_proba(X)[:, 1])
            wsum += self.weights["rf"]
        if self.weights["svm"] > 0:
            parts.append(self.weights["svm"] * self._svm_proba(Xs))
            wsum += self.weights["svm"]
        if not parts or wsum == 0:
            return np.full((X.shape[0], 2), 0.5)
        p1 = np.sum(parts, axis=0) / wsum
        p1 = np.clip(p1, 0.0, 1.0)
        return np.stack([1 - p1, p1], axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

    @property
    def feature_importances_(self) -> Optional[np.ndarray]:
        """Mean importance across available tree models (None if absent)."""
        imps, sizes = [], []
        if self.xgb is not None:
            imps.append(self.xgb.feature_importances_)
            sizes.append(len(self.xgb.feature_importances_))
        if self.rf is not None:
            imps.append(self.rf.feature_importances_)
            sizes.append(len(self.rf.feature_importances_))
        if not imps:
            return None
        n = max(sizes)
        total = np.zeros(n)
        for imp in imps:
            total[: len(imp)] += imp
        return total / len(imps)
