#!/usr/bin/env python3
"""qc_fast.py — universal QC runner (any file, any size).

Used by the Next.js API routes via subprocess. Prints exactly ONE JSON line
to stdout (the report); all logs go to stderr. Exit codes:
  0 success   2 insufficient RAM (memory guard)   3 input error

Memory strategy (PART 3.6):
  * memory guard: exit 2 if available RAM < 300 MB
  * MAX_CELLS subsampling (default 500; override with RESIPSC_MAX_CELLS)
  * backed mode for h5ad files > 50 MB (read only the subsample)
  * forced gc.collect() after preprocessing
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from resipsc.utils.logging import get_logger

LOGGER = get_logger("qc_fast")

MIN_FREE_MB = 300
MAX_CELLS = int(os.environ.get("RESIPSC_MAX_CELLS", "500"))
BACKED_THRESHOLD_MB = 50
SUPPORTED = (".h5ad", ".csv", ".tsv", ".mtx", ".txt", ".h5", ".parquet")


def _available_mb() -> float:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        info = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
        return info.get("MemAvailable", 0) / 1024.0
    except Exception:  # noqa: BLE001
        return 4096.0


def _fail(code: int, message: str) -> None:
    print(json.dumps({"status": "error", "message": message, "exit_code": code}))
    raise SystemExit(code)


def load_input(path: str):
    """Load any supported single-cell file into an AnnData-like object."""
    import anndata as ad

    if not os.path.exists(path):
        _fail(3, f"file not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    size_mb = os.path.getsize(path) / 1e6
    if ext not in SUPPORTED:
        _fail(3, f"unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED)}")

    backed = ext == ".h5ad" and size_mb > BACKED_THRESHOLD_MB
    if ext == ".h5ad":
        try:
            a = ad.read_h5ad(path, backed="r" if backed else None)
        except Exception as exc:  # noqa: BLE001 - retry without backing
            LOGGER.warning("h5ad load failed (%s); retrying backed", exc)
            try:
                a = ad.read_h5ad(path, backed="r")
            except Exception as exc2:  # noqa: BLE001
                _fail(3, f"cannot read h5ad: {exc2}")
    elif ext in (".csv", ".tsv", ".txt"):
        import pandas as pd

        sep = "," if ext == ".csv" else "\t"
        try:
            df = pd.read_csv(path, sep=sep, index_col=0)
        except Exception as exc:  # noqa: BLE001
            _fail(3, f"cannot read csv/tsv: {exc}")
        if df.shape[0] < df.shape[1]:  # probably genes x cells — transpose
            df = df.T
        from scipy import sparse

        a = ad.AnnData(
            X=sparse.csr_matrix(df.values.astype(np.float32)),
            obs=pd.DataFrame(index=[str(i) for i in df.index]),
            var=pd.DataFrame(index=[str(c) for c in df.columns]),
        )
        a.obs["dataset_id"] = "csv_upload"
        a.obs["is_psc"] = 0
    elif ext == ".mtx":
        import pandas as pd
        from scipy import sparse

        try:
            M = sparse.csr_matrix(np.loadtxt(path))  # small matrices
        except Exception:  # noqa: BLE001
            import scipy.io as sio

            M = sparse.csr_matrix(sio.mmread(path))
        base = os.path.dirname(path)
        genes_path = next(
            (os.path.join(base, f) for f in os.listdir(base) if f.startswith("genes")),
            None,
        )
        var_names = None
        if genes_path and os.path.exists(genes_path):
            gdf = pd.read_csv(genes_path, sep="\t", header=None)
            var_names = [str(v) for v in gdf[gdf.columns[-1]].values]
        a = ad.AnnData(X=M.astype(np.float32))
        if var_names is not None:
            a.var_names = var_names
        a.obs["dataset_id"] = "mtx_upload"
        a.obs["is_psc"] = 0
    elif ext == ".h5":
        try:
            a = ad.read_10x_h5(path)
        except Exception as exc:  # noqa: BLE001
            _fail(3, f"cannot read 10x h5: {exc}")
        a.obs["dataset_id"] = "10x_upload"
        a.obs["is_psc"] = 0
    else:  # parquet
        import pandas as pd

        try:
            df = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            _fail(3, f"cannot read parquet: {exc}")
        if df.shape[0] < df.shape[1]:
            df = df.T
        a = ad.AnnData(X=df.values.astype(np.float32))
        a.obs["dataset_id"] = "parquet_upload"
        a.obs["is_psc"] = 0
    LOGGER.info("loaded %s: %d cells x %d genes (%.1f MB, backed=%s)",
                os.path.basename(path), a.n_obs, a.n_vars, size_mb, backed)
    return a, backed


def subsample(a, max_cells: int, seed: int = 0):
    """Random cell subsample to bound memory; returns a copy."""
    if a.n_obs <= max_cells:
        try:
            return a.to_memory().copy() if hasattr(a, "to_memory") else a.copy()
        except Exception:  # noqa: BLE001
            return a.copy()
    rng = np.random.default_rng(seed)
    keep = np.sort(rng.choice(a.n_obs, size=max_cells, replace=False))
    sub = a[keep]
    try:
        sub = sub.to_memory().copy() if hasattr(sub, "to_memory") else sub.copy()
    except Exception:  # noqa: BLE001
        pass
    LOGGER.info("subsampled %d -> %d cells", a.n_obs, max_cells)
    return sub


def run_qc(input_path: str, model, batch_id: str = "BATCH-000") -> dict:
    """Run the full QC pipeline on one file with an existing trained model."""
    from resipsc.models.ensemble import ResipscEnsemble  # noqa: F401

    a, backed = load_input(input_path)
    original_cells = int(a.n_obs)
    a_sub = subsample(a, MAX_CELLS)
    del a
    gc.collect()

    report = model.qc_report_dict(a_sub, batch_id=batch_id, input_file=input_path)
    del a_sub
    gc.collect()

    # annotate subsampling + provenance
    report["input_total_cells"] = original_cells
    report["subsampled"] = bool(original_cells > MAX_CELLS)
    report["max_cells_cap"] = MAX_CELLS
    if original_cells > MAX_CELLS:
        report["qc_flags"].insert(
            0,
            {
                "severity": "warning",
                "category": "subsample",
                "message": (
                    f"Input had {original_cells} cells; analysis subsampled to "
                    f"{MAX_CELLS} for memory safety (RESIPSC_MAX_CELLS)."
                ),
                "action": "Set RESIPSC_MAX_CELLS higher on machines with more RAM.",
            },
        )
        # keep severity ordering
        order = {"critical": 0, "warning": 1, "info": 2}
        report["qc_flags"].sort(key=lambda f: order.get(f["severity"], 3))
    report["model_fitted"] = bool(getattr(model, "fitted", True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--batch-id", default=None)
    parser.add_argument("--model", default="results/final_model.pkl")
    parser.add_argument("--save", default="1", help="save report JSON to results/qc_reports")
    args = parser.parse_args()

    free_mb = _available_mb()
    if free_mb < MIN_FREE_MB:
        _fail(2, f"insufficient RAM: {free_mb:.0f} MB available (< {MIN_FREE_MB} MB)")

    from resipsc.compliance.audit import AuditTrail
    from resipsc.utils.io import load_pickle, save_json

    trail = AuditTrail()
    batch_id = args.batch_id or os.path.splitext(os.path.basename(args.input))[0][:24].upper()

    try:
        model = load_pickle(args.model)
    except Exception as exc:  # noqa: BLE001
        _fail(3, f"cannot load model ({args.model}): {exc}")

    t0 = __import__("time").time()
    trail.log("qc_run_started", "qc_report", batch_id,
              new_value={"input": args.input}, user_id="api")
    try:
        report = run_qc(args.input, model, batch_id=batch_id)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        trail.log("qc_run_failed", "qc_report", batch_id,
                  old_value=None, new_value={"error": str(exc)[:500]}, user_id="api")
        _fail(3, f"QC failed: {exc}")
    dt = __import__("time").time() - t0

    report["runtime_seconds"] = round(dt, 2)
    report["status"] = "ok"

    # persist the report
    if args.save == "1":
        os.makedirs("results/qc_reports", exist_ok=True)
        out_path = os.path.join(
            "results", "qc_reports", f"{batch_id}_{report['report_metadata']['report_id'][:12]}.json"
        )
        save_json(report, out_path)
        report["saved_report_path"] = out_path

    # calibration check (drift monitoring) + audit completion
    try:
        from resipsc.validation.calibration import CalibrationMonitor

        cm = CalibrationMonitor()
        Xs, _ = model.featurize(load_input(args.input)[0])
        p = model.predict_proba(Xs)[:, 1]
        cm.check(p, batch_id=batch_id)
    except Exception as exc:  # noqa: BLE001 - non-fatal
        LOGGER.warning("calibration check skipped: %s", exc)

    trail.log(
        "qc_run_completed", "qc_report", batch_id,
        new_value={
            "decision": report.get("decision"),
            "n_cells": report.get("n_cells"),
            "psc_fraction_pct": round(100 * (report.get("estimated_psc_fraction") or 0), 4),
            "report_id": report["report_metadata"]["report_id"],
        },
        reason="automated QC via API", user_id="api",
    )

    print(json.dumps(report, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
