#!/usr/bin/env python3
"""make_large_test.py — generate a large (default 557 MB) h5ad test file.

Memory-bounded: the dense matrix is written row-chunk by row-chunk directly
through h5py into the h5ad layout anndata reads, so the generator never
holds the full matrix in RAM (the naive AnnData-in-memory approach OOMs on
4 GB machines at the default size).

Usage: python scripts/make_large_test.py [--mb 557] [--out data/large_test.h5ad]
"""

from __future__ import annotations

import argparse
import os

import h5py
import numpy as np


def write_big_h5ad(path: str, target_mb: float, n_genes: int = 30000) -> tuple[int, int]:
    """Write a dense h5ad of ~target_mb MB with PSC-like marker rows."""
    bytes_total = int(target_mb * 1e6)
    n_cells = max(100, bytes_total // (n_genes * 4))
    rng = np.random.default_rng(42)

    marker_cols = list(range(0, 8))  # pretend these are POU5F1..ESRG slots
    n_psc = max(1, n_cells // 10000)

    with h5py.File(path, "w") as f:
        X = f.create_dataset(
            "X", shape=(n_cells, n_genes), dtype="f4",
            chunks=(64, 2048), compression=None,
        )
        # obs group
        obs = f.create_group("obs")
        obs.create_dataset(
            "_index",
            data=np.array([f"cell_{i:07d}" for i in range(n_cells)], dtype=h5py.string_dtype("utf-8")),
        )
        labels = np.zeros(n_cells, dtype="i1")
        labels[:n_psc] = 1
        rng.shuffle(labels)
        obs.create_dataset("is_psc", data=labels)
        obs.create_dataset(
            "dataset_id",
            data=np.array(["large_test"] * n_cells, dtype=h5py.string_dtype("utf-8")),
        )
        # var group
        var = f.create_group("var")
        var.create_dataset(
            "_index",
            data=np.array([f"gene_{j:06d}" for j in range(n_genes)], dtype=h5py.string_dtype("utf-8")),
        )
        # write in bounded row chunks
        CH = 256
        for start in range(0, n_cells, CH):
            stop = min(start + CH, n_cells)
            block = rng.lognormal(0, 1, (stop - start, n_genes)).astype("f4")
            # marker spikes in PSC rows
            row_sel = np.where(labels[start:stop] == 1)[0]
            if len(row_sel):
                block[np.ix_(row_sel, marker_cols)] = np.log1p(800.0).astype("f4")
            X[start:stop] = block
    return n_cells, n_genes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mb", type=float, default=557.0)
    ap.add_argument("--out", default="data/large_test.h5ad")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    n_cells, n_genes = write_big_h5ad(args.out, args.mb)
    size = os.path.getsize(args.out) / 1e6
    print(f"OK wrote {args.out}: {n_cells} x {n_genes}, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
