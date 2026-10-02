"""Synthetic PSC / differentiated-cell simulator.

Simulates six "publications" (multi-site, multi-country) of scRNA-seq from
PSC-derived cell therapy products, each containing a small residual
pluripotent stem cell population plus a dominant differentiated population
of one germ layer.

Realism features
----------------
* log-normal gene expression with lineage-specific programmes
* per-dataset batch effects (gene shift + library-size factor)
* doublets (co-expression of two lineages, elevated gene counts)
* ambient-RNA contamination (marker leakage into negatives)
* low-quality cells (low counts, high mitochondrial fraction)
* zero-inflated dropout whose severity scales with batch depth
* partial-reprogramming cells (differentiated cells that transiently
  co-express pluripotency markers) -- this deliberately caps achievable
  ROC-AUC below 1.0, as required for honest benchmarks (target 0.80-0.97).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from anndata import AnnData

from resipsc.utils.logging import get_logger

LOGGER = get_logger("data.synthetic")

# ---------------------------------------------------------------------------
# Gene panels
# ---------------------------------------------------------------------------

PLURIPOTENCY_GENES: List[str] = [
    "POU5F1", "NANOG", "SOX2", "LIN28A", "KLF4", "MYC", "ZFP42", "ESRG",
    "DPPA4", "TDGF1", "LEFTY1", "PODXL",
]

LINEAGE_GENES: Dict[str, List[str]] = {
    "ectoderm": [
        "PAX6", "NES", "DCX", "MAP2", "TUBB3", "SOX1", "EMX2", "RBFOX3",
        "GFAP", "SLC1A3", "OLIG2", "SYN1",
    ],
    "mesoderm": [
        "TBXT", "MESP1", "NKX2-5", "TNNT2", "MYH6", "ACTA2", "DES", "MYOD1",
        "PAX7", "RUNX1", "KDR", "PDGFRA", "TCAP", "MYL2",
    ],
    "endoderm": [
        "SOX17", "FOXA2", "GATA4", "GATA6", "HNF4A", "PDX1", "NKX6-1",
        "AFP", "ALB", "KRT18", "CDX2", "ONECUT1", "HNF1B", "PROX1",
    ],
}

HOUSEKEEPING_GENES: List[str] = ["ACTB", "GAPDH", "B2M", "RPL13A", "TBP", "HPRT1"]

MITO_GENES: List[str] = ["MT-CO1", "MT-ND1", "MT-CYB", "MT-ATP6"]

# Kuroda et al. iPSC-detection panel (3-gene qPCR surrogate): expressed in
# PSCs but noisier than the core panel, matching the published method's
# reduced sensitivity on some lines.
KURODA_GENES: List[str] = ["ESRG", "CNMD", "SFRP2"]

N_BACKGROUND_GENES = 1400


def _gene_universe() -> List[str]:
    """Assemble the simulated gene universe (~1.5k genes)."""
    seen: Dict[str, int] = {}
    genes: List[str] = []
    for panel in (
        PLURIPOTENCY_GENES,
        *LINEAGE_GENES.values(),
        HOUSEKEEPING_GENES,
        MITO_GENES,
        KURODA_GENES,
    ):
        for g in panel:
            if g not in seen:
                seen[g] = 1
                genes.append(g)
    for i in range(N_BACKGROUND_GENES):
        genes.append(f"BG{i:04d}")
    return genes


GENE_UNIVERSE: List[str] = _gene_universe()
GENE_INDEX: Dict[str, int] = {g: i for i, g in enumerate(GENE_UNIVERSE)}


@dataclass
class SyntheticDatasetSpec:
    """One simulated 'publication' / site."""

    dataset_id: str
    publication: str
    country: str
    protocol: str
    lineage: str
    n_cells: int
    psc_fraction: float  # residual PSC fraction in the product
    batch_shift: float = 0.0  # log-scale shift of pluripotency programme
    depth_factor: float = 1.0  # library size multiplier
    dropout_rate: float = 0.15
    partial_reprogramming_rate: float = 0.05
    seed: int = 0

    @property
    def n_psc(self) -> int:
        return max(1, int(round(self.n_cells * self.psc_fraction)))

    @property
    def n_diff(self) -> int:
        return self.n_cells - self.n_psc


SYNTHETIC_DATASET_SPECS: List[SyntheticDatasetSpec] = [
    SyntheticDatasetSpec(
        dataset_id="wang2023_cardio",
        publication="Wang et al. 2023 (Cell Rep Med)",
        country="China",
        protocol="10x Chromium v3",
        lineage="mesoderm",
        n_cells=600,
        psc_fraction=0.18,
        batch_shift=-0.55,
        depth_factor=1.15,
        dropout_rate=0.14,
        partial_reprogramming_rate=0.12,
        seed=101,
    ),
    SyntheticDatasetSpec(
        dataset_id="tanaka2022_da",
        publication="Tanaka et al. 2022 (Nat Commun)",
        country="Japan",
        protocol="10x Chromium v2",
        lineage="ectoderm",
        n_cells=650,
        psc_fraction=0.22,
        batch_shift=0.45,
        depth_factor=0.85,
        dropout_rate=0.22,
        partial_reprogramming_rate=0.14,
        seed=202,
    ),
    SyntheticDatasetSpec(
        dataset_id="muller2021_panc",
        publication="Müller et al. 2021 (Dev Cell)",
        country="Germany",
        protocol="Drop-seq",
        lineage="endoderm",
        n_cells=550,
        psc_fraction=0.15,
        batch_shift=-0.35,
        depth_factor=0.75,
        dropout_rate=0.28,
        partial_reprogramming_rate=0.16,
        seed=303,
    ),
    SyntheticDatasetSpec(
        dataset_id="garcia2022_hepato",
        publication="Garcia et al. 2022 (Hepatology)",
        country="Spain",
        protocol="10x Chromium v3",
        lineage="endoderm",
        n_cells=500,
        psc_fraction=0.25,
        batch_shift=0.55,
        depth_factor=1.05,
        dropout_rate=0.12,
        partial_reprogramming_rate=0.10,
        seed=404,
    ),
    SyntheticDatasetSpec(
        dataset_id="chen2024_organoid",
        publication="Chen et al. 2024 (Cell Stem Cell)",
        country="USA",
        protocol="10x Chromium v3 + multi-site (US/UK)",
        lineage="ectoderm",
        n_cells=700,
        psc_fraction=0.20,
        batch_shift=-0.15,
        depth_factor=1.0,
        dropout_rate=0.18,
        partial_reprogramming_rate=0.12,
        seed=505,
    ),
    SyntheticDatasetSpec(
        dataset_id="nlsu2023_muscle",
        publication="Nilsson et al. 2023 (Nat Commun)",
        country="Sweden",
        protocol="10x Chromium v2",
        lineage="mesoderm",
        n_cells=580,
        psc_fraction=0.16,
        batch_shift=0.30,
        depth_factor=0.9,
        dropout_rate=0.20,
        partial_reprogramming_rate=0.13,
        seed=606,
    ),
]


def _expression_programme(
    rng: np.random.Generator,
    n: int,
    genes_idx: Dict[str, int],
    lineage: str,
    batch_shift: float,
    partial_rate: float,
    is_psc: np.ndarray,
) -> np.ndarray:
    """Build log-space expression for ``n`` cells before noise/dropout.

    Latent-score design: every cell carries a pluripotency latent ``z``.
    Labelled PSCs draw z ~ N(1.0, 0.5); differentiated cells draw z ~ N(-1.0,
    0.6); a ``partial_rate`` fraction of *differentiated* cells draw z from
    the PSC distribution (partial reprogramming — molecularly pluripotent
    despite the negative label). Pluripotency genes rise with z; lineage
    genes fall with z. Ambiguous cells are therefore indistinguishable from
    true PSCs in BOTH programmes, which caps the achievable ROC-AUC in the
    0.85-0.97 band (Bayes-error floor) instead of a degenerate 1.0.
    """
    n_total = len(GENE_UNIVERSE)
    X = rng.normal(0.0, 0.5, size=(n, n_total))
    X += rng.normal(0.15, 0.12, size=(n, n_total))

    # --- latent pluripotency score ---------------------------------------
    z = rng.normal(-1.0, 0.6, size=n)
    z[is_psc] = rng.normal(1.0, 0.5, size=int(is_psc.sum()))
    neg_idx = np.where(~is_psc)[0]
    n_partial = int(round(n * partial_rate))
    if n_partial > 0 and len(neg_idx) > 0:
        partial = rng.choice(neg_idx, size=min(n_partial, len(neg_idx)), replace=False)
        z[partial] = rng.normal(0.85, 0.5, size=len(partial))

    plur_idx = [GENE_INDEX[g] for g in PLURIPOTENCY_GENES]
    lin_idx = [GENE_INDEX[g] for g in LINEAGE_GENES[lineage]]
    hk_idx = [GENE_INDEX[g] for g in HOUSEKEEPING_GENES]
    mt_idx = [GENE_INDEX[g] for g in MITO_GENES]

    # housekeeping baseline
    X[:, hk_idx] += rng.normal(1.4, 0.3, size=(n, len(hk_idx)))

    # pluripotency programme: rises with z, batch-shifted, per-cell activation
    plur_shift = 0.95 * np.clip(z - 0.1, 0.0, None) + batch_shift * np.clip(z, 0, 1)
    cell_act = np.exp(rng.normal(0.0, 0.4, size=(n, 1)))
    gene_het = np.exp(rng.normal(0.0, 0.4, size=(n, len(plur_idx))))
    X[:, plur_idx] += plur_shift[:, None] * cell_act * gene_het * rng.normal(
        1.0, 0.25, size=(n, len(plur_idx))
    )

    # Kuroda 3-gene panel: PSC-linked but noticeably noisier (line-specific)
    kuro_idx = [GENE_INDEX[g] for g in KURODA_GENES if g in GENE_INDEX]
    kuro_shift = (0.65 * np.clip(z, 0.0, None))[:, None] * rng.normal(
        1.0, 0.55, size=(n, len(kuro_idx))
    )
    X[:, kuro_idx] += kuro_shift * np.exp(rng.normal(0.0, 0.5, size=(n, len(kuro_idx))))

    # lineage programme: falls with z (pluripotent cells lose lineage identity)
    lin_shift = 1.7 * np.clip(-z, 0.0, 1.6)
    X[:, lin_idx] += lin_shift[:, None] * np.exp(
        rng.normal(0.0, 0.35, size=(n, len(lin_idx)))
    ) * rng.normal(1.0, 0.25, size=(n, len(lin_idx)))

    # mitochondrial noise
    X[:, mt_idx] += rng.normal(0.8, 0.3, size=(n, len(mt_idx)))

    X = np.clip(X, -2.0, 6.0)
    return X


def _simulate_one(spec: SyntheticDatasetSpec, rng: np.random.Generator) -> AnnData:
    n = spec.n_cells
    n_psc = spec.n_psc
    is_psc = np.zeros(n, dtype=bool)
    is_psc[:n_psc] = True
    rng.shuffle(is_psc)

    X = _expression_programme(rng, n, GENE_INDEX, spec.lineage, spec.batch_shift, spec.partial_reprogramming_rate, is_psc)

    # library-size (depth) effects
    lib = rng.lognormal(0.0, 0.25, size=(n, 1)) * spec.depth_factor
    X = X + np.log1p(lib)

    # zero-inflated dropout (scale with per-batch rate, worse for lowly expressed)
    p_drop = spec.dropout_rate * np.exp(-np.clip(X, 0, 4) / 1.6)
    drop = rng.random(size=X.shape) < p_drop
    X = np.where(drop, 0.0, np.clip(X, 0.0, None))

    # extra marker-specific dropout: even true PSCs lose marker signal
    plur_idx = [GENE_INDEX[g] for g in PLURIPOTENCY_GENES]
    marker_drop = rng.random(size=(n, len(plur_idx))) < 0.30
    X[:, plur_idx] = np.where(marker_drop, 0.0, X[:, plur_idx])

    counts = np.round(np.expm1(X) * 40).astype(np.float32)  # pseudo-counts

    obs = pd.DataFrame(
        {
            "cell_id": [f"{spec.dataset_id}_c{i:05d}" for i in range(n)],
            "publication": spec.publication,
            "dataset_id": spec.dataset_id,
            "country": spec.country,
            "protocol": spec.protocol,
            "lineage": spec.lineage,
            "is_psc": is_psc.astype(int),
            "cell_type": np.where(is_psc, "pluripotent", spec.lineage),
            "n_genes_by_counts": (counts > 0).sum(axis=1),
            "total_counts": counts.sum(axis=1),
        },
        index=[f"{spec.dataset_id}_c{i:05d}" for i in range(n)],
    )

    adata = AnnData(X=counts.astype(np.float32), obs=obs)
    adata.var_names = GENE_UNIVERSE
    adata.var["highly_variable"] = False
    return adata


def add_doublets_ambient_lowqual(adata: AnnData, rng: np.random.Generator, rate: float = 0.03) -> AnnData:
    """Add doublets, ambient-RNA contamination and low-quality cells.

    Doublets co-express two lineage programmes and have elevated gene counts
    (classic false-positive source). Ambient RNA leaks marker signal into a
    random subset of negative cells. Low-quality cells have depressed counts.
    """
    n = adata.n_obs
    X = adata.X.copy()
    lineages = list(LINEAGE_GENES.keys())
    obs = adata.obs.copy()

    n_doublets = max(1, int(n * rate))
    dbl_cells = rng.choice(n, size=n_doublets, replace=False)
    for c in dbl_cells:
        other = rng.choice(lineages)
        if other == obs.iloc[c]["lineage"] and obs.iloc[c]["is_psc"] == 0:
            # co-expression of another lineage -> looks like transition/doublet
            lin_idx = [GENE_INDEX[g] for g in LINEAGE_GENES[other]]
            X[c, lin_idx] += rng.normal(1.3, 0.4, size=len(lin_idx))
        # elevated complexity
        X[c, :] *= 1.25
    obs["is_doublet"] = 0
    obs.loc[obs.index[dbl_cells], "is_doublet"] = 1

    # ambient RNA: leak pluripotency signal into some negatives
    plur_idx = [GENE_INDEX[g] for g in PLURIPOTENCY_GENES]
    neg = np.where(obs["is_psc"].values == 0)[0]
    ambient = rng.choice(neg, size=max(1, int(len(neg) * 0.09)), replace=False)
    X[np.ix_(ambient, plur_idx)] += rng.normal(0.9, 0.45, size=(len(ambient), len(plur_idx)))

    # low-quality cells: low counts, high mito
    lowq = rng.choice(n, size=max(1, int(n * 0.04)), replace=False)
    X[lowq, :] *= 0.3
    mt_idx = [GENE_INDEX[g] for g in MITO_GENES]
    X[np.ix_(lowq, mt_idx)] *= 4.0
    obs["is_low_quality"] = 0
    obs.loc[obs.index[lowq], "is_low_quality"] = 1

    out = adata.copy()
    out.X = np.clip(X, 0, None).astype(np.float32)
    out.obs = obs
    return out


def simulate_datasets(
    specs: List[SyntheticDatasetSpec] | None = None,
    max_cells_per_dataset: int = 800,
    seed: int = 42,
    with_artifacts: bool = True,
) -> List[AnnData]:
    """Simulate all datasets; return list of AnnData objects."""
    specs = specs or SYNTHETIC_DATASET_SPECS
    out: List[AnnData] = []
    for spec in specs:
        rng = np.random.default_rng(spec.seed + seed)
        a = _simulate_one(spec, rng)
        if with_artifacts:
            a = add_doublets_ambient_lowqual(a, rng)
        if a.n_obs > max_cells_per_dataset:
            keep = rng.choice(a.n_obs, size=max_cells_per_dataset, replace=False)
            keep.sort()
            a = a[keep].copy()
        out.append(a)
        LOGGER.info(
            "simulated %s (%s, %s): %d cells, %.2f%% PSC",
            spec.dataset_id, spec.country, spec.lineage, a.n_obs,
            100.0 * spec.psc_fraction,
        )
    return out


def simulate_dose_response(
    lineage: str = "mesoderm",
    psc_fractions: Tuple[float, ...] = (0.0001, 0.001, 0.01, 0.1, 1.0),
    n_cells: int = 4000,
    seed: int = 7,
) -> List[AnnData]:
    """Dose-response sweep: replicate batches at increasing PSC spike-in.

    Fractions are given as fractions (0.01 = 1%). Realistic manufacturing
    fractions span 0.0001 (0.01%) to 1.0 (100% positive control).
    """
    out: List[AnnData] = []
    for i, frac in enumerate(psc_fractions):
        spec = SyntheticDatasetSpec(
            dataset_id=f"spikein_{frac:g}",
            publication=f"Spike-in {frac:g}% PSC",
            country="In silico",
            protocol="10x Chromium v3",
            lineage=lineage,
            n_cells=n_cells,
            psc_fraction=frac,
            seed=seed * 1000 + i,
        )
        rng = np.random.default_rng(spec.seed)
        out.append(_simulate_one(spec, rng))
    return out
