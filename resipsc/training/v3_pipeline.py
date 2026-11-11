"""
Resipsc V3 Complete Training Pipeline
Orchestrates: Real Data -> scVI -> Gating -> Evidential Calibration
"""

import torch
import numpy as np
import anndata as ad
from pathlib import Path
from typing import Dict, Any
from resipsc.data.real_acquisition import prepare_training_corpus
from resipsc.models.scvi_trainer import train_v3_foundation_model, ResipscSCVI
from resipsc.models.gating_layer import build_v3_gating_model, HierarchicalGatingNet
from resipsc.utils.logging import get_logger

LOGGER = get_logger("v3.pipeline")

def train_v3_complete(
    data_dir: str = "data/real",
    output_dir: str = "models/v3_complete",
    device: str = "cpu",
    **kwargs
) -> Dict[str, Any]:
    """
    Complete V3 training pipeline.
    
    Pipeline stages:
    1. Download & harmonize real human data (Wellington + negatives)
    2. Train scVI foundation model (invariant latent space)
    3. Build hierarchical gating network
    4. Joint fine-tuning with evidential loss
    5. EVT calibration on tail
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    LOGGER.info("=" * 60)
    LOGGER.info("RESIPSC V3 COMPLETE TRAINING PIPELINE")
    LOGGER.info("=" * 60)
    
    # Stage 1: Real Data Acquisition
    LOGGER.info("Stage 1: Real Data Acquisition")
    corpus, panel = prepare_training_corpus(data_dir)
    
    # Save harmonized corpus
    corpus_path = output_path / "training_corpus.h5ad"
    corpus.write_h5ad(corpus_path)
    LOGGER.info(f"Saved training corpus to {corpus_path}")
    
    # Stage 2: scVI Foundation Model
    LOGGER.info("Stage 2: scVI Foundation Model Training")
    scvi_model, latent = train_v3_foundation_model(
        corpus,
        output_dir=str(output_path / "scvi"),
        **kwargs
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
        gating_model, latent_tensor, labels, device
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
    epochs: int = 100,
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
        # L = sum(y * (digamma(S) - digamma(alpha))) + KL(Dir(alpha) || Dir(1))
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
        
        if epoch % 20 == 0:
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
    
    # Focus on positive class tail
    pos_probs = probs[true_labels == 1]
    if len(pos_probs) < 10:
        LOGGER.warning("Insufficient positive samples for EVT calibration")
        return
    
    # Peak Over Threshold (POT) - fit GPD to top 10%
    threshold = np.percentile(pos_probs, 90)
    exceedances = pos_probs[pos_probs > threshold] - threshold
    
    if len(exceedances) < 5:
        return
    
    # Simple method of moments for GPD
    mean_exceed = exceedances.mean()
    var_exceed = exceedances.var()
    
    if var_exceed > 0:
        shape = 0.5 * (1 - (mean_exceed**2 / var_exceed))
        scale = 0.5 * mean_exceed * (1 + (mean_exceed**2 / var_exceed))
    else:
        shape, scale = 0.1, mean_exceed
    
    LOGGER.info(f"EVT Calibration: threshold={threshold:.4f}, shape={shape:.4f}, scale={scale:.4f}")
    
    # Store in model (as buffer for inference)
    model.register_buffer("evt_threshold", torch.tensor(threshold))
    model.register_buffer("evt_shape", torch.tensor(shape))
    model.register_buffer("evt_scale", torch.tensor(scale))

def save_v3_model(
    scvi_model: ResipscSCVI,
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
