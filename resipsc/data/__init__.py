"""Data loading, simulation, and preprocessing for resipsc."""

from resipsc.data.synthetic import (
    SyntheticDatasetSpec,
    SYNTHETIC_DATASET_SPECS,
    simulate_datasets,
    simulate_dose_response,
    add_doublets_ambient_lowqual,
)
from resipsc.data.preprocessing import preprocess_anndata, matrix_from_anndata
from resipsc.data.acquisition import download_census_dataset, download_pbmc3k

__all__ = [
    "SyntheticDatasetSpec",
    "SYNTHETIC_DATASET_SPECS",
    "simulate_datasets",
    "simulate_dose_response",
    "add_doublets_ambient_lowqual",
    "preprocess_anndata",
    "matrix_from_anndata",
    "download_census_dataset",
    "download_pbmc3k",
]
