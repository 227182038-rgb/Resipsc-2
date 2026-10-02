"""Autoencoder embedding: TruncatedSVD projection + MLP autoencoder.

Design (RAM-friendly):
  1. TruncatedSVD reduces the HVG matrix to ``n_components`` latent dims
     (linear "encoder" init).
  2. A small sklearn MLPRegressor autoencoder is trained to reconstruct the
     SVD latent space; the bottleneck activations form the embedding used by
     the downstream MLP classifier.

If the AE fails to converge within the iteration budget, we silently fall
back to the raw SVD projection (never crash a QC run over an embedding).
"""

from __future__ import annotations

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.neural_network import MLPRegressor

from resipsc.utils.logging import get_logger

LOGGER = get_logger("features.embedding")


class AutoencoderEmbedder:
    """TruncatedSVD + MLP autoencoder feature embedder."""

    def __init__(
        self,
        n_components: int = 32,
        ae_epochs: int = 10,
        hidden: tuple = (64, 32),
        random_state: int = 42,
    ) -> None:
        self.n_components = n_components
        self.ae_epochs = ae_epochs
        self.hidden = hidden
        self.random_state = random_state
        self.svd: TruncatedSVD | None = None
        self.ae: MLPRegressor | None = None
        self._fitted = False

    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray) -> "AutoencoderEmbedder":
        n_comp = int(min(self.n_components, max(2, X.shape[1] - 1), X.shape[0]))
        self.svd = TruncatedSVD(n_components=n_comp, random_state=self.random_state)
        Z = self.svd.fit_transform(X)

        # max_iter generous; early_stopping does the real stopping (PART 3.8)
        max_iter = max(2000, self.ae_epochs * 200)
        self.ae = MLPRegressor(
            hidden_layer_sizes=(self.hidden[0], n_comp, self.hidden[0]),
            activation="relu",
            max_iter=max_iter,
            early_stopping=True,
            n_iter_no_change=10,
            validation_fraction=0.15,
            random_state=self.random_state,
        )
        try:
            self.ae.fit(Z, Z)
        except Exception as exc:  # noqa: BLE001 - fall back to raw SVD space
            LOGGER.warning("AE training failed (%s); using SVD space", exc)
            self.ae = None
        self._fitted = True
        return self

    # ------------------------------------------------------------------
    def transform(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted or self.svd is None:
            raise RuntimeError("AutoencoderEmbedder not fitted")
        Z = self.svd.transform(X)
        if self.ae is not None:
            try:
                Z = self.ae.predict(Z)
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("AE predict failed (%s); using SVD space", exc)
        return np.asarray(Z, dtype=np.float32)

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)
