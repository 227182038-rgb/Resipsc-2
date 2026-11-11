"""Resipsc V3 scVI Foundation Model Training
Trains invariant variational autoencoder for batch-corrected latent space.
Replaces 292-HVG static feature extraction with 32-dim learned representation.
"""

import os
import json
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import anndata as ad
import torch
import scvi
from scvi.model import SCVI
from resipsc.utils.logging import get_logger

LOGGER = get_logger("v3.models.scvi_trainer")

MODEL_DIR = Path("models/v3_scvi")


class ResipscSCVI:
    """Wrapper for scVI model with Resipsc-specific configuration.
    Learns batch-invariant latent representation for PSC detection.
    """

    def __init__(
        self,
        n_latent: int = 32,
        n_layers: int = 2,
        n_hidden: int = 256,
        dropout_rate: float = 0.1,
        gene_likelihood: str = "nb",
        dispersion: str = "gene-batch",
        **kwargs
    ):
        self.n_latent = n_latent
        self.n_layers = n_layers
        self.n_hidden = n_hidden
        self.dropout_rate = dropout_rate
        self.gene_likelihood = gene_likelihood
        self.dispersion = dispersion
        self.kwargs = kwargs
        self.model: Optional[SCVI] = None
        self.adata_ref: Optional[ad.AnnData] = None

    def setup_anndata(self, adata: ad.AnnData, batch_key: str = "dataset_id", labels_key: str = "lineage"):
        """Register AnnData with scVI."""
        if batch_key not in adata.obs.columns:
            adata.obs[batch_key] = "batch_0"
        if labels_key not in adata.obs.columns:
            adata.obs[labels_key] = "unknown"

        if "counts" not in adata.layers:
            pass

        SCVI.setup_anndata(
            adata,
            batch_key=batch_key,
            labels_key=labels_key,
            layer="counts" if "counts" in adata.layers else None
        )
        self.adata_ref = adata

    def train(
        self,
        adata: ad.AnnData,
        max_epochs: int = 200,
        batch_size: int = 256,
        early_stopping: bool = True,
        plan_kwargs: Optional[dict] = None,
        **trainer_kwargs
    ) -> "ResipscSCVI":
        """Train the scVI model."""
        self.setup_anndata(adata)

        self.model = SCVI(
            adata,
            n_latent=self.n_latent,
            n_layers=self.n_layers,
            n_hidden=self.n_hidden,
            dropout_rate=self.dropout_rate,
            gene_likelihood=self.gene_likelihood,
            dispersion=self.dispersion,
            **self.kwargs
        )

        # Training with early stopping
        callbacks = []
        if early_stopping:
            try:
                from scvi.train import EarlyStopping
                callbacks.append(EarlyStopping(
                    monitor="elbo_validation",
                    patience=20,
                    mode="min"
                ))
            except ImportError:
                try:
                    from lightning.pytorch.callbacks import EarlyStopping
                    callbacks.append(EarlyStopping(
                        monitor="elbo_validation",
                        patience=20,
                        mode="min"
                    ))
                except ImportError:
                    LOGGER.warning("EarlyStopping not available, training without early stopping")
                    early_stopping = False

        plan_kwargs = plan_kwargs or {"lr": 1e-3}

        self.model.train(
            max_epochs=max_epochs,
            batch_size=batch_size,
            early_stopping=early_stopping,
            plan_kwargs=plan_kwargs,
            **trainer_kwargs
        )

        try:
            elbo_train = self.model.history['elbo_train'].iloc[-1] if hasattr(self.model.history['elbo_train'], 'iloc') else self.model.history['elbo_train'][-1]
            LOGGER.info(f"scVI training completed. ELBO: {elbo_train:.4f}")
        except Exception:
            LOGGER.info("scVI training completed.")
        return self

    def get_latent(self, adata: ad.AnnData = None) -> np.ndarray:
        """Get latent representation for cells."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        target = adata or self.adata_ref
        if target is None:
            raise ValueError("No AnnData provided")
        return self.model.get_latent_representation(target)

    def get_normalized_expression(self, adata: ad.AnnData = None, n_samples: int = 25) -> np.ndarray:
        """Get denoised/normalized expression (library-size corrected)."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        target = adata or self.adata_ref
        return self.model.get_normalized_expression(target, n_samples=n_samples)

    def save(self, path: str):
        """Save model and metadata."""
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        self.model.save(p, overwrite=True)

        metadata = {
            "n_latent": self.n_latent,
            "n_layers": self.n_layers,
            "n_hidden": self.n_hidden,
            "dropout_rate": self.dropout_rate,
            "gene_likelihood": self.gene_likelihood,
            "dispersion": self.dispersion
        }
        with open(p / "resipsc_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        LOGGER.info(f"Saved scVI model to {path}")

    @classmethod
    def load(cls, path: str, adata: ad.AnnData = None) -> "ResipscSCVI":
        """Load model from disk."""
        p = Path(path)
        with open(p / "resipsc_metadata.json", "r") as f:
            metadata = json.load(f)

        instance = cls(**metadata)
        instance.model = SCVI.load(p, adata=adata)
        return instance


def train_v3_foundation_model(
    training_corpus: ad.AnnData,
    output_dir: str = "models/v3_scvi",
    **kwargs
) -> Tuple[ResipscSCVI, np.ndarray]:
    """
    Complete V3 foundation model training pipeline.

    Args:
        training_corpus: Harmonized AnnData from real_acquisition
        output_dir: Model save directory

    Returns:
        Tuple of (trained_model, latent_representations)
    """
    LOGGER.info("Starting V3 scVI foundation model training...")

    if "counts" not in training_corpus.layers:
        LOGGER.warning("No 'counts' layer found. Using .X as proxy (may be log-normalized).")

    trainer = ResipscSCVI(
        n_latent=32,
        n_layers=2,
        n_hidden=256,
        dropout_rate=0.1,
        gene_likelihood="nb",
        dispersion="gene-batch"
    )

    train_kwargs = {
        'max_epochs': kwargs.get('max_epochs', 200),
        'batch_size': kwargs.get('batch_size', 256),
        'early_stopping': kwargs.get('early_stopping', True),
        'plan_kwargs': kwargs.get('plan_kwargs', {'lr': 1e-3}),
    }
    for key in ['max_epochs', 'batch_size', 'early_stopping', 'plan_kwargs']:
        kwargs.pop(key, None)

    trainer.train(training_corpus, **train_kwargs, **kwargs)

    latent = trainer.get_latent(training_corpus)

    trainer.save(output_dir)

    LOGGER.info(f"Latent space shape: {latent.shape}")
    LOGGER.info(f"Model saved to {output_dir}")

    return trainer, latent