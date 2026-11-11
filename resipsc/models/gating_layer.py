"""Resipsc V3 Hierarchical Biological Prior Net
Implements dual-branch network with inhibitory mature lineage blockers.
Prevents false positives from partial differentiation / ambient RNA.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional
import numpy as np

LINEAGE_MARKERS = {
    "ectoderm": ["PAX6", "NES", "DCX", "MAP2", "TUBB3", "SOX1", "GFAP", "RBFOX3"],
    "mesoderm": ["TBXT", "MESP1", "NKX2-5", "TNNT2", "MYH6", "ACTA2", "DES", "MYOD1"],
    "endoderm": ["SOX17", "FOXA2", "GATA4", "GATA6", "HNF4A", "PDX1", "AFP", "ALB"],
    "cardiac": ["TNNT2", "MYH6", "MYH7", "ACTN2", "TNNC1", "RYR2"],
    "neuronal": ["TH", "MAP2", "DCX", "TUBB3", "SYN1", "RBFOX3"],
    "rpe": ["RPE65", "BEST1", "TYR", "MLANA", "MITF", "PMEL"],
    "hepatic": ["ALB", "AFP", "HNF4A", "CYP3A4", "TTR", "APOB"],
}

PLURIPOTENCY_MARKERS = [
    "POU5F1", "SOX2", "NANOG", "LIN28A", "DPPA2", "DPPA4",
    "ZFP42", "SALL4", "PRDM14", "UTF1", "EPCAM", "PODXL",
]


class InhibitoryGatingLayer(nn.Module):
    """
    Bi-directional gating mechanism:
    - Pluripotency branch: activates on pluripotency markers
    - Lineage branch: activates on mature markers
    - Inhibitory gate: lineage activation suppresses pluripotency score
    """

    def __init__(
        self,
        input_dim: int,
        gene_names: List[str],
        hidden_dim: int = 64,
        inhibition_strength: float = 2.0
    ):
        super().__init__()
        self.gene_names = gene_names
        self.inhibition_strength = inhibition_strength
        self.hidden_dim = hidden_dim

        # Map gene names to indices
        self.pluri_indices = [i for i, g in enumerate(gene_names) if g in PLURIPOTENCY_MARKERS]
        self.lineage_indices = {}
        for lineage, markers in LINEAGE_MARKERS.items():
            idx = [i for i, g in enumerate(gene_names) if g in markers]
            if idx:
                self.lineage_indices[lineage] = idx

        # Learnable gating parameters
        self.pluri_proj = nn.Linear(len(self.pluri_indices), hidden_dim)
        self.lineage_projs = nn.ModuleDict({
            lin: nn.Linear(len(idx), hidden_dim)
            for lin, idx in self.lineage_indices.items()
        })

        # Integration layer
        n_lineages = len(self.lineage_indices)
        self.integration = nn.Sequential(
            nn.Linear(hidden_dim * (1 + n_lineages), hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, 1)
        )

        # Learnable inhibition weights per lineage
        self.inhibition_weights = nn.ParameterDict({
            lin: nn.Parameter(torch.ones(1) * inhibition_strength)
            for lin in self.lineage_indices
        })

    def _ensure_2d(self, x: torch.Tensor, expected_features: int = None) -> torch.Tensor:
        """Ensure tensor is 2D (batch, features)."""
        if x.dim() == 1:
            x = x.unsqueeze(0)
        elif x.dim() == 3:
            if x.shape[1] == 1:
                x = x.squeeze(1)
            else:
                x = x.reshape(x.shape[0], -1)
        elif x.dim() > 3:
            x = x.reshape(x.shape[0], -1)

        if expected_features is not None and x.shape[1] != expected_features:
            # Try to reshape if it's a multiple
            if x.numel() // x.shape[0] == expected_features:
                x = x.reshape(x.shape[0], expected_features)
        return x

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch_size, n_genes) - normalized expression
        Returns:
            gated_scores: (batch_size, 1) - inhibited pluripotency scores
        """
        # Ensure input is 2D
        x = self._ensure_2d(x)
        batch_size = x.shape[0]

        # Pluripotency pathway
        pluri_features = x[:, self.pluri_indices]  # (B, n_pluri)
        pluri_hidden = self.pluri_proj(pluri_features)  # (B, H)
        pluri_hidden = self._ensure_2d(pluri_hidden, self.hidden_dim)

        # Lineage pathways with inhibition
        lineage_hiddens = []
        for lineage, idx in self.lineage_indices.items():
            lineage_feat = x[:, idx]  # (B, n_lineage)
            lineage_feat = self._ensure_2d(lineage_feat, len(idx))
            lineage_hidden = self.lineage_projs[lineage](lineage_feat)  # (B, H)
            lineage_hidden = self._ensure_2d(lineage_hidden, self.hidden_dim)

            # Apply inhibitory gate: high lineage activity suppresses pluripotency
            inhibition = torch.sigmoid(lineage_hidden.mean(dim=1, keepdim=True)) * self.inhibition_weights[lineage]
            pluri_hidden = pluri_hidden * (1 - inhibition)

            lineage_hiddens.append(lineage_hidden)

        # Ensure all tensors are 2D with correct feature dim before concat
        pluri_hidden = self._ensure_2d(pluri_hidden, self.hidden_dim)
        lineage_hiddens_2d = [self._ensure_2d(h, self.hidden_dim) for h in lineage_hiddens]

        # Concatenate inhibited pluripotency + lineage signals
        combined = torch.cat([pluri_hidden] + lineage_hiddens_2d, dim=1)

        # Final integration
        output = self.integration(combined)
        return torch.sigmoid(output)  # Probability of residual PSC


class HierarchicalGatingNet(nn.Module):
    """
    Complete V3 hierarchical network combining:
    1. scVI latent encoder (frozen or fine-tuned)
    2. Inhibitory gating layer
    3. Evidential output head (Dirichlet)
    """

    def __init__(
        self,
        scvi_latent_dim: int = 32,
        n_genes: int = 60,
        gene_names: List[str] = None,
        hidden_dim: int = 128,
        n_lineages: int = 7
    ):
        super().__init__()
        self.gene_names = gene_names or []

        # Latent to gene decoder (maps scVI latent back to gene space for gating)
        self.latent_to_gene = nn.Sequential(
            nn.Linear(scvi_latent_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_genes)
        )

        # Inhibitory gating layer
        self.gating = InhibitoryGatingLayer(
            input_dim=n_genes,
            gene_names=self.gene_names,
            hidden_dim=hidden_dim
        )

        # Evidential head (outputs Dirichlet parameters alpha)
        self.evidential_head = nn.Sequential(
            nn.Linear(1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 2),  # alpha_0 (non-PSC), alpha_1 (PSC)
            nn.Softplus()  # Ensure positive
        )

        # Calibration head for EVT
        self.evt_head = nn.Sequential(
            nn.Linear(1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 3)  # GPD parameters: loc, scale, shape
        )

    def forward(self, latent: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Args:
            latent: (batch_size, 32) - scVI latent representation
        Returns:
            Dict with probabilities, Dirichlet alphas, EVT parameters
        """
        # Ensure latent is 2D
        if latent.dim() == 1:
            latent = latent.unsqueeze(0)
        elif latent.dim() == 3:
            latent = latent.squeeze(1) if latent.shape[1] == 1 else latent.view(latent.shape[0], -1)

        batch_size = latent.shape[0]

        # Decode to gene space
        gene_recon = self.latent_to_gene(latent)  # (B, n_genes)
        gene_recon = torch.relu(gene_recon)  # Expression is non-negative

        # Apply inhibitory gating
        psc_prob = self.gating(gene_recon)  # (B, 1)

        # Evidential output
        alphas = self.evidential_head(psc_prob) + 1  # (B, 2) - Dirichlet alphas
        total_alpha = alphas.sum(dim=1, keepdim=True)

        # Probability from Dirichlet mean
        prob_psc = alphas[:, 1:2] / total_alpha

        # Uncertainty decomposition
        # Aleatoric = expected variance
        aleatoric = (alphas[:, 1:2] * alphas[:, 0:1]) / (total_alpha**2 * (total_alpha + 1))
        # Epistemic = model uncertainty (from total evidence)
        epistemic = 2 / (total_alpha + 2)

        # EVT tail parameters
        evt_params = self.evt_head(psc_prob)

        return {
            "prob_psc": prob_psc,
            "alphas": alphas,
            "aleatoric_uncertainty": aleatoric,
            "epistemic_uncertainty": epistemic,
            "evt_params": evt_params,
            "gated_features": gene_recon
        }


def build_v3_gating_model(gene_names: List[str]) -> HierarchicalGatingNet:
    """Factory function for V3 gating model."""
    return HierarchicalGatingNet(
        scvi_latent_dim=32,
        n_genes=len(gene_names),
        gene_names=gene_names,
        hidden_dim=128
    )