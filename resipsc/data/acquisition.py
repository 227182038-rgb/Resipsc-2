"""cellxgene Census / public dataset acquisition.

Downloads real datasets for hybrid training and evaluation. All download
functions stream to disk and return the local path. If a dataset is already
present, the path is returned immediately.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Optional

from resipsc.utils.logging import get_logger

LOGGER = get_logger("data.acquisition")

# Wellington iPSC integration dataset (PART 7 of spec): 41,670 cells x 23,290 genes
WELLINGTON_CENSUS_ID = "5b0e8244-cc05-47ab-819f-87747854c04c"
WELLINGTON_URL = (
    "https://datasets.cellxgene.cziscience.com/"
    "5b0e8244-cc05-47ab-819f-87747854c04c.h5ad"
)

PBMC3K_URLS = [
    "https://datasets.cellxgene.cziscience.com/"
    "cddab57b-6868-4be9-9d7b-1daed2ff9758.h5ad",
    "https://raw.githubusercontent.com/scverse/scanpy-tutorials/master/pbmc3k.h5ad",
]


def _download(url: str, dest: Path, timeout: int = 600) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("downloading %s -> %s", url, dest)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=timeout) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(tmp, dest)
    LOGGER.info("downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def download_census_dataset(
    dataset_id: str = WELLINGTON_CENSUS_ID,
    data_dir: str = "data/real",
) -> Optional[Path]:
    """Download the Wellington iPSC integration dataset (~599 MB)."""
    dest = Path(data_dir) / "iPSC_integration_41k.h5ad"
    if dest.exists():
        return dest
    try:
        return _download(WELLINGTON_URL, dest)
    except Exception as exc:  # noqa: BLE001 - network may be unavailable
        LOGGER.warning("census download failed: %s", exc)
        return None


def download_pbmc3k(data_dir: str = "data") -> Optional[Path]:
    """Download the classic 3k PBMC dataset (~5.9 MB, 2,700 cells)."""
    dest = Path(data_dir) / "pbmc3k_raw.h5ad"
    if dest.exists():
        return dest
    for url in PBMC3K_URLS:
        try:
            return _download(url, dest)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("pbmc3k source failed (%s): %s", url, exc)
    return None


def _use_raw_and_set_symbols(a):
    """Map Ensembl IDs to gene symbols via var['feature_name'] (PART 7)."""
    import anndata as ad

    if "feature_name" in a.var.columns:
        a.var["gene_symbol"] = a.var["feature_name"]
    a.var["feature_id"] = a.var_names
    a.var_names = a.var["gene_symbol"].astype(str).values
    a = a[:, ~a.var.index.duplicated(keep="first")].copy()
    return a
