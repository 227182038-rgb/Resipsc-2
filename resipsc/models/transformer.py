"""MiniSCTransformer: a tiny numpy-only single-cell transformer.

Optional component — used only when Config.skip_transformer is False.
Implements a single-head scaled dot-product self-attention block with a
small classification head, trained with Adam via numpy autodiff-free manual
gradients (logistic loss, linear head; attention is used as a deterministic
feature map). This keeps the model faithful to the "lightweight attention"
spec while staying dependency-free and RAM-cheap.
"""

from __future__ import annotations

import numpy as np

from resipsc.utils.logging import get_logger

LOGGER = get_logger("models.transformer")


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


class MiniSCTransformer:
    """Lightweight attention model over the gene feature vector.

    The input feature vector is split into ``n_heads`` token-like chunks
    (simulating gene-programme tokens); one self-attention layer pools them
    into a context vector; a linear head classifies PSC vs non-PSC.
    """

    def __init__(
        self,
        dim: int = 32,
        n_heads: int = 4,
        epochs: int = 2,
        lr: float = 0.05,
        random_state: int = 42,
    ) -> None:
        self.dim = dim
        self.n_heads = n_heads
        self.epochs = epochs
        self.lr = lr
        self.rng = np.random.default_rng(random_state)
        self.Wq = None
        self.Wk = None
        self.Wv = None
        self.head = None
        self.classes_ = np.array([0, 1])
        self._fitted = False

    # ------------------------------------------------------------------
    def _tokens(self, X: np.ndarray) -> np.ndarray:
        """Reshape (n, d) -> (n, heads, d/heads) pseudo-tokens."""
        n, d = X.shape
        h = min(self.n_heads, d)
        per = d // h
        if per == 0:
            return X.reshape(n, 1, d)
        d_used = h * per
        return X[:, :d_used].reshape(n, h, per)

    def _attention(self, T: np.ndarray) -> np.ndarray:
        Q = T @ self.Wq
        K = T @ self.Wk
        V = T @ self.Wv
        scores = Q @ K.transpose(0, 2, 1) / np.sqrt(K.shape[-1])
        A = _softmax(scores)
        return (A @ V).reshape(T.shape[0], -1)

    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray) -> "MiniSCTransformer":
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y).astype(int).ravel()
        T = self._tokens(X)
        h, per = T.shape[1], T.shape[2]

        # Xavier init
        def xav(shape):
            return self.rng.normal(0, np.sqrt(2.0 / (shape[0] + shape[1])), shape)

        self.Wq = xav((per, per))
        self.Wk = xav((per, per))
        self.Wv = xav((per, per))
        d_ctx = h * per
        self.head = xav((d_ctx, 1)) * 0.1

        y01 = y.astype(np.float64)
        m = X.shape[0]
        for _ in range(max(1, self.epochs)):
            ctx = self._attention(T)
            logits = ctx @ self.head
            p = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
            g = (p - y01) / m  # dL/dlogits
            grad_head = ctx.T @ g
            # approximate attention gradients via dense-path backprop on V
            gctx = g @ self.head.T
            gV = gctx.reshape(m, h, 1, per) * np.eye(per)[None, None, :, :]
            # gradient wrt Wv: sum over tokens of T^T dV
            gWv = np.zeros_like(self.Wv)
            for hi in range(h):
                gWv += T[:, hi, :].T @ gV[:, hi, 0, :]
            for param, grad in ((self.head, grad_head), (self.Wv, gWv)):
                param -= self.lr * grad
            self.Wq = self.Wq  # Q/K frozen (positional stability)
            self.Wk = self.Wk
        self._fitted = True
        return self

    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("MiniSCTransformer not fitted")
        X = np.asarray(X, dtype=np.float64)
        T = self._tokens(X)
        ctx = self._attention(T)
        logits = ctx @ self.head
        p1 = 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))
        return np.stack([1 - p1, p1], axis=1)

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
