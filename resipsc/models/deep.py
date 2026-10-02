"""Deep model: Autoencoder embedding + MLP classifier with calibration."""

from __future__ import annotations

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier

from resipsc.features.embedding import AutoencoderEmbedder
from resipsc.utils.logging import get_logger

LOGGER = get_logger("models.deep")


class MLPClassifierModel:
    """Autoencoder (TruncatedSVD + MLP) embedder with an MLP head.

    Training: embed -> scale -> MLP classifier (early stopping on a
    validation split). If classifier calibration via CalibratedClassifierCV
    is feasible it is applied; otherwise raw predict_proba is used.
    """

    def __init__(
        self,
        n_components: int = 32,
        ae_epochs: int = 10,
        mlp_hidden: tuple = (64, 32),
        mlp_epochs: int = 60,
        random_state: int = 42,
    ) -> None:
        self.n_components = n_components
        self.ae_epochs = ae_epochs
        self.mlp_hidden = mlp_hidden
        self.mlp_epochs = mlp_epochs
        self.random_state = random_state

        self.embedder = AutoencoderEmbedder(
            n_components=n_components, ae_epochs=ae_epochs,
            random_state=random_state,
        )
        self.clf: MLPClassifier | CalibratedClassifierCV | None = None
        self.classes_ = np.array([0, 1])
        self._fitted = False

    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "MLPClassifierModel":
        X = np.asarray(X, dtype=np.float32)
        y = np.asarray(y).astype(int)
        self.classes_ = np.unique(y)

        Z = self.embedder.fit_transform(X)

        # PART 3.8: generous max_iter; early_stopping does the real stopping
        base = MLPClassifier(
            hidden_layer_sizes=self.mlp_hidden,
            activation="relu",
            max_iter=max(2000, self.mlp_epochs * 20),
            early_stopping=True,
            n_iter_no_change=10,
            validation_fraction=0.15,
            random_state=self.random_state,
        )
        try:
            n_splits = int(min(3, np.bincount(y).min()))
            if n_splits >= 2:
                cv = StratifiedKFold(n_splits=n_splits, shuffle=True,
                                     random_state=self.random_state)
                self.clf = CalibratedClassifierCV(base, method="sigmoid", cv=cv)
                self.clf.fit(Z, y)
            else:
                raise ValueError("too few samples for CV")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("MLP calibration failed (%s); raw MLP", exc)
            self.clf = base.fit(Z, y)
        self._fitted = True
        return self

    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted or self.clf is None:
            raise RuntimeError("MLPClassifierModel not fitted")
        Z = self.embedder.transform(np.asarray(X, dtype=np.float32))
        return self.clf.predict_proba(Z)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
