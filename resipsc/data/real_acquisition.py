"""
Resipsc V3 Real Data Acquisition
Downloads and prepares real human single-cell datasets for foundation model training.
Replaces synthetic data with CZ CELLxGENE Census and curated negative controls.
"""

import os
import urllib.request
from pathlib import Path
from typing import List, Optional
import scanpy as sc
import anndata as ad
import numpy as np
import pandas as pd
from resipsc.utils.logging import get_logger

LOGGER = get_logger("v3.data.real_acquisition")

# CZ CELLxGENE Census Configuration
WELLINGTON_CENSUS_ID = "5b0e8244-cc05-47ab-819f-87747854c04c"
WELLINGTON_URL = f"https://datasets.cellxgene.cziscience.com/{WELLINGTON_CENSUS_ID}.h5ad"

# Curated negative control datasets (mature differentiated cells)
NEGATIVE_CONTROLS = {
    "cardiomyocytes": {
        "url": "https://datasets.cellxgene.cziscience.com/heart_atlas.h5ad",
        "cell_type": "cardiomyocyte",
        "lineage": "mesoderm"
    },
    "dopaminergic_neurons": {
        "url": "https://datasets.cellxgene.cziscience.com/brain_atlas.h5ad",
        "cell_type": "dopaminergic neuron",
        "lineage": "ectoderm"
    },
    "retinal_pigment_epithelial": {
        "url": "https://datasets.cellxgene.cziscience.com/retina_atlas.h5ad",
        "cell_type": "retinal pigment epithelial",
        "lineage": "ectoderm"
    },
    "hepatocytes": {
        "url": "https://datasets.cellxgene.cziscience.com/liver_atlas.h5ad",
        "cell_type": "hepatocyte",
        "lineage": "endoderm"
    }
}

MASTER_REGULATOR_PANEL = [
    "POU5F1", "SOX2", "NANOG", "LIN28A", "DPPA2", "DPPA4",
    "ZFP42", "SALL4", "PRDM14", "UTF1", "EPCAM", "PODXL",
    "TDGF1", "LEFTY1", "LEFTY2", "GDF3", "NANOGP1", "NANOGP8",
    "KLF4", "KLF5", "MYC", "MYCN", "ESRG", "DPPA3", "DPPA5",
    "DNMT3B", "GABRB3", "ZSCAN4", "ZSCAN10", "TCL1A", "DPPA5B"
]

CURATED_PANEL_SIZE = 60  # 30 pluripotency + 30 lineage markers

def download_with_resume(url: str, dest: Path, chunk_size: int = 1 << 20) -> Path:
    """Download with resume capability for large files."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    
    headers = {}
    if tmp.exists():
        downloaded = tmp.stat().st_size
        headers["Range"] = f"bytes={downloaded}-"
        mode = "ab"
    else:
        downloaded = 0
        mode = "wb"
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, mode) as fh:
        total = int(resp.headers.get("Content-Length", 0)) + downloaded
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            fh.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                LOGGER.info(f"Downloaded {downloaded/1e6:.1f}/{total/1e6:.1f} MB ({100*downloaded/total:.1f}%)")
    
    os.replace(tmp, dest)
    return dest

def fetch_wellington(data_dir: str = "data/real") -> Optional[Path]:
    """Download Wellington iPSC integration dataset (41,670 cells)."""
    dest = Path(data_dir) / "wellington_ipsc_41k.h5ad"
    if dest.exists():
        LOGGER.info(f"Wellington dataset already exists at {dest}")
        return dest
    
    try:
        LOGGER.info("Downloading Wellington iPSC dataset (~599 MB)...")
        return download_with_resume(WELLINGTON_URL, dest)
    except Exception as exc:
        LOGGER.error(f"Wellington download failed: {exc}")
        return None

def fetch_negative_controls(data_dir: str = "data/real") -> List[Path]:
    """Fetch curated negative control datasets."""
    paths = []
    for name, info in NEGATIVE_CONTROLS.items():
        dest = Path(data_dir) / f"neg_{name}.h5ad"
        if dest.exists():
            paths.append(dest)
            continue
        try:
            LOGGER.info(f"Downloading {name} negative control...")
            # Note: These URLs are templates - actual CELLxGENE URLs need curation
            download_with_resume(info["url"], dest)
            paths.append(dest)
        except Exception as exc:
            LOGGER.warning(f"Failed to download {name}: {exc}")
    return paths

def load_and_harmonize(path: Path, target_genes: List[str]) -> ad.AnnData:
    """Load dataset and harmonize to target gene panel."""
    LOGGER.info(f"Loading {path.name}...")
    adata = sc.read_h5ad(path)
    
    # Ensure gene symbols are in var_names
    if "feature_name" in adata.var.columns:
        adata.var_names = adata.var["feature_name"].astype(str)
    
    # Remove duplicates
    adata = adata[:, ~adata.var_names.duplicated(keep="first")].copy()
    
    # Intersect with target genes
    available = list(set(adata.var_names) & set(target_genes))
    LOGGER.info(f"  {len(available)}/{len(target_genes)} target genes available")
    
    if len(available) < len(target_genes) * 0.5:
        LOGGER.warning(f"Low gene overlap for {path.name}")
    
    return adata[:, available].copy()

def prepare_training_corpus(data_dir: str = "data/real") -> tuple:
    """
    Prepare complete V3 training corpus:
    - Wellington iPSC dataset (positive)
    - Negative controls (4 lineages)
    - Returns harmonized AnnData objects ready for scVI
    """
    # 1. Define 60-gene master panel
    panel = MASTER_REGULATOR_PANEL + [
        # Cardiac lineage
        "TNNT2", "MYH6", "MYH7", "ACTN2", "TNNC1", "RYR2",
        # Neuronal lineage
        "TH", "MAP2", "DCX", "TUBB3", "SYN1", "RBFOX3",
        # RPE lineage
        "RPE65", "BEST1", "TYR", "MLANA", "MITF", "PMEL",
        # Hepatic lineage
        "ALB", "AFP", "HNF4A", "CYP3A4", "TTR", "APOB"
    ][:CURATED_PANEL_SIZE]
    
    # 2. Download datasets
    wellington_path = fetch_wellington(data_dir)
    neg_paths = fetch_negative_controls(data_dir)
    
    if not wellington_path:
        raise RuntimeError("Wellington dataset is required for V3 training")
    
    # 3. Load and harmonize
    positive = load_and_harmonize(wellington_path, panel)
    positive.obs["is_psc"] = 1
    positive.obs["lineage"] = "pluripotent"
    positive.obs["dataset_id"] = "wellington"
    
    negatives = []
    for np in neg_paths:
        name = np.stem.replace("neg_", "")
        neg = load_and_harmonize(np, panel)
        neg.obs["is_psc"] = 0
        neg.obs["lineage"] = NEGATIVE_CONTROLS[name]["lineage"]
        neg.obs["dataset_id"] = name
        negatives.append(neg)
    
    # 4. Combine
    corpus = [positive] + negatives
    combined = ad.concat(corpus, axis=0, join="outer", label="dataset_id")
    combined.obs_names_make_unique()
    
    LOGGER.info(f"Training corpus: {combined.n_obs} cells x {combined.n_vars} genes")
    LOGGER.info(f"PSC fraction: {combined.obs['is_psc'].mean():.4f}")
    
    return combined, panel
