"""Deterministic seeding across python/numpy/random."""

from __future__ import annotations

import random

import numpy as np


def seed_everything(seed: int = 42) -> None:
    """Seed python, numpy and set PYTHONHASHSEED for reproducibility."""
    import os

    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
