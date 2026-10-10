#!/usr/bin/env python3
"""calibration_api.py — calibration drift endpoints for the API routes.

Usage:
  python scripts/calibration_api.py --status
  python scripts/calibration_api.py --check <path> --batch-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--check", default=None)
    ap.add_argument("--batch-id", default="BATCH-000")
    args = ap.parse_args()

    from resipsc.utils.io import load_pickle
    from resipsc.validation.calibration import CalibrationMonitor

    cm = CalibrationMonitor()

    if args.status:
        print(json.dumps(cm.status(), default=str))
        return 0

    if args.check:
        if not os.path.exists(args.check):
            print(json.dumps({"status": "error", "message": f"file not found: {args.check}"}))
            return 3
        try:
            model = load_pickle("results/final_model.pkl")
            Xs, _ = model.featurize(_load_any(args.check))
            p = model.predict_proba(Xs)[:, 1]
            res = cm.check(p, batch_id=args.batch_id)
            res["status"] = "ok"
            print(json.dumps(res, default=str))
            return 0
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"status": "error", "message": str(exc)[:500]}))
            return 3

    print(json.dumps({"status": "error", "message": "no action"}))
    return 1


def _load_any(path: str):
    import anndata as ad

    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        import pandas as pd

        df = pd.read_csv(path, index_col=0)
        if df.shape[0] < df.shape[1]:
            df = df.T
        return ad.AnnData(X=df.values.astype("float32"),
                           obs={"dataset_id": "csv"}, var=pd.DataFrame(index=list(df.columns)))
    return ad.read_h5ad(path)


if __name__ == "__main__":
    raise SystemExit(main())
