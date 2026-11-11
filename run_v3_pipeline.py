#!/usr/bin/env python
"""
Resipsc V3 Complete Training Pipeline - Synthetic Data Version
Runs the complete V3 pipeline using synthetic data for testing.
"""

import sys
import torch
import numpy as np
import anndata as ad
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, r'E:\resipsc v2 final 1')

from resipsc.data.synthetic import simulate_datasets
from resipsc.models.scvi_trainer import train_v3_foundation_model, ResipscSCVI
from resipsc.models.gating_layer import build_v3_gating_model, HierarchicalGatingNet
from resipsc.utils.logging import get_logger

import torch
import torch.nn as nn
import torch.nn.functional as F

LOGGER = get_logger("v3.pipeline.synthetic")

def train_v3_complete_synthetic(
    datasets,
    output_dir: str = "models/v3_complete",
    device: str = "cpu",
    **kwargs
) -> Dict[str, Any]:
    """
    Complete V3 training pipeline using pre-generated synthetic datasets.
    """
    import anndata as ad
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    LOGGER.info("=" * 60)
    LOGGER.info("RESIPSC V3 COMPLETE TRAINING PIPELINE (SYNTHETIC)")
    LOGGER.info("=" * 60)

    # Stage 1: Use provided synthetic datasets
    LOGGER.info("Stage 1: Synthetic Data Preparation")
    corpus = ad.concat(datasets, axis=0, join="outer", label="dataset_id")
    corpus.obs_names_make_unique()

    # Build 60-gene panel (same as real_acquisition)
    panel = [
        "POU5F1", "SOX2", "NANOG", "LIN28A", "DPPA2", "DPPA4",
        "ZFP42", "SALL4", "PRDM14", "UTF1", "EPCAM", "PODXL",
        "TDGF1", "LEFTY1", "LEFTY2", "GDF3", "NANOGP1", "NANOGP8",
        "KLF4", "KLF5", "MYC", "MYCN", "ESRG", "DPPA3", "DPPA5",
        "DNMT3B", "GABRB3", "ZSCAN4", "ZSCAN10", "TCL1A", "DPPA5B",
        "TNNT2", "MYH6", "MYH7", "ACTN2", "TNNC1", "RYR2",
        "TH", "MAP2", "DCX", "TUBB3", "SYN1", "RBFOX3",
        "RPE65", "BEST1", "TYR", "MLANA", "MITF", "PMEL",
        "ALB", "AFP", "HNF4A", "CYP3A4", "TTR", "APOB"
    ][:60]

    # Harmonize corpus to panel
    available = list(set(corpus.var_names) & set(panel))
    LOGGER.info(f"  {len(available)}/{len(panel)} target genes available")
    corpus = corpus[:, available].copy()

    # Add labels
    if "is_psc" not in corpus.obs.columns:
        corpus.obs["is_psc"] = 0
    if "lineage" not in corpus.obs.columns:
        corpus.obs["lineage"] = "unknown"
    if "dataset_id" not in corpus.obs.columns:
        corpus.obs["dataset_id"] = "synthetic"

    # Save harmonized corpus
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    corpus_path = output_path / "training_corpus.h5ad"
    corpus.write_h5ad(corpus_path)
    LOGGER.info(f"Saved training corpus to {corpus_path}")
    LOGGER.info(f"Training corpus: {corpus.n_obs} cells x {corpus.n_vars} genes")
    LOGGER.info(f"PSC fraction: {corpus.obs['is_psc'].mean():.4f}")

    # Stage 2: scVI Foundation Model
    LOGGER.info("Stage 2: scVI Foundation Model Training")
    scvi_model, latent = train_v3_foundation_model(
        corpus,
        output_dir=str(output_path / "scvi"),
        max_epochs=20,
        batch_size=64
    )

    # Stage 3: Hierarchical Gating Network
    LOGGER.info("Stage 3: Hierarchical Gating Network Construction")
    gating_model = build_v3_gating_model(panel)
    gating_model.to(device)

    # Prepare labels for supervised gating
    labels = torch.tensor(corpus.obs["is_psc"].values, dtype=torch.float32).unsqueeze(1)
    latent_tensor = torch.tensor(latent, dtype=torch.float32).to(device)

    # Stage 4: Joint Training (Evidential Loss)
    LOGGER.info("Stage 4: Evidential Fine-tuning")
    gating_model = train_evidential_gating(
        gating_model, latent_tensor, labels, device, epochs=50, lr=1e-3
    )

    # Stage 5: EVT Calibration
    LOGGER.info("Stage 5: EVT Tail Calibration")
    calibrate_evt_tail(gating_model, latent_tensor, labels, device)

    # Save complete model
    save_v3_model(
        scvi_model, gating_model, panel, output_path
    )

    return {
        "scvi_model": scvi_model,
        "gating_model": gating_model,
        "panel": panel,
        "latent": latent,
        "output_dir": str(output_path)
    }


def train_evidential_gating(
    model: HierarchicalGatingNet,
    latent: torch.Tensor,
    labels: torch.Tensor,
    device: str,
    epochs: int = 50,
    lr: float = 1e-3
) -> HierarchicalGatingNet:
    """Train gating network with Dirichlet evidential loss."""
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    for epoch in range(epochs):
        optimizer.zero_grad()

        outputs = model(latent)
        alphas = outputs["alphas"]

        # Dirichlet evidential loss
        S = alphas.sum(dim=1, keepdim=True)
        loss = torch.mean(
            torch.sum(labels * (torch.digamma(S) - torch.digamma(alphas)), dim=1)
        )

        # KL regularization toward uniform
        target_alpha = torch.ones_like(alphas)
        kl_loss = torch.mean(
            torch.sum(
                (alphas - target_alpha) * (torch.digamma(alphas) - torch.digamma(S)),
                dim=1
            )
        )

        total_loss = loss + 0.1 * kl_loss
        total_loss.backward()
        optimizer.step()
        scheduler.step()

        if epoch % 10 == 0:
            LOGGER.info(f"  Epoch {epoch}: loss={loss.item():.4f}, kl={kl_loss.item():.4f}")

    model.eval()
    return model


def calibrate_evt_tail(
    model: HierarchicalGatingNet,
    latent: torch.Tensor,
    labels: torch.Tensor,
    device: str
):
    """Fit Generalized Pareto Distribution to prediction tail."""
    model.eval()
    with torch.no_grad():
        outputs = model(latent)
        probs = outputs["prob_psc"].cpu().numpy().flatten()
        true_labels = labels.cpu().numpy().flatten()

    pos_probs = probs[true_labels == 1]
    if len(pos_probs) < 10:
        LOGGER.warning("Insufficient positive samples for EVT calibration")
        return

    threshold = np.percentile(pos_probs, 90)
    exceedances = pos_probs[pos_probs > threshold] - threshold

    if len(exceedances) < 5:
        return

    mean_exceed = exceedances.mean()
    var_exceed = exceedances.var()

    if var_exceed > 0:
        shape = 0.5 * (1 - (mean_exceed**2 / var_exceed))
        scale = 0.5 * mean_exceed * (1 + (mean_exceed**2 / var_exceed))
    else:
        shape, scale = 0.1, mean_exceed

    LOGGER.info(f"EVT Calibration: threshold={threshold:.4f}, shape={shape:.4f}, scale={scale:.4f}")

    model.register_buffer("evt_threshold", torch.tensor(threshold))
    model.register_buffer("evt_shape", torch.tensor(shape))
    model.register_buffer("evt_scale", torch.tensor(scale))


def save_v3_model(
    scvi_model,
    gating_model: HierarchicalGatingNet,
    panel: list,
    output_path: Path
):
    """Save complete V3 model package."""
    # Save scVI
    scvi_model.save(str(output_path / "scvi"))

    # Save gating network
    torch.save({
        "model_state_dict": gating_model.state_dict(),
        "gene_panel": panel,
        "architecture": "HierarchicalGatingNet",
        "version": "3.0.0"
    }, output_path / "gating_net.pt")

    LOGGER.info(f"Complete V3 model saved to {output_path}")


def main():
    """Main entry point for V3 pipeline with synthetic data."""
    from resipsc.data.synthetic import simulate_datasets

    # Generate synthetic datasets
    datasets = simulate_datasets(max_cells_per_dataset=200, seed=42)

    LOGGER.info("=" * 60)
    LOGGER.info("RESIPSC V3 COMPLETE TRAINING PIPELINE (SYNTHETIC)")
    LOGGER.info("=" * 60)

    result = train_v3_complete_synthetic(
        datasets,
        output_dir="models/v3_complete",
        device="cpu",
        max_epochs=20,
        batch_size=64
    )

    LOGGER.info("V3 Pipeline completed successfully!")
    print("\nResult keys:", list(result.keys()))
    if "gating_model" in result:
        print("Gating model type:", type(result["gating_model"]))
    if "latent" in result:
        print("Latent shape:", result["latent"].shape)


if __name__ == "__main__":
    main()