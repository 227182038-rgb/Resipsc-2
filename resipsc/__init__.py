"""resipsc — residual pluripotent stem cell detection for cell therapy QC.

resipsc (Residual Pluripotent Stem Cell) v2.0 is a machine-learning system
that detects residual pluripotent stem cells (PSCs) in single-cell RNA-seq
data of cell therapy products, estimates the residual PSC fraction, assigns
germ-layer lineage identity to detected cells, and maps teratoma risk to
22 anatomical sites with literature-derived priors.

Intended use: research use only. NOT FDA-cleared. See the disclaimer
emitted with every QC report.
"""

from __future__ import annotations

import os

__version__ = "2.0.0"

# --- Environment shim (PART 3.1) --------------------------------------------
# The Next.js .env sets DATABASE_URL for Prisma, but anndata's pydantic
# settings reads it and crashes. Pop it before any anndata import happens.
# sitecustomize.py covers interpreter startup; this covers direct imports.
os.environ.pop("DATABASE_URL", None)
os.environ.pop("DATABASE_URL_FILE", None)

from resipsc.config import Config, default_config  # noqa: E402

__all__ = ["Config", "default_config", "__version__"]
