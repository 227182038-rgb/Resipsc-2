"""CLI entry point for the resipsc package.

Usage:
  python -m resipsc.cli train --mode hybrid
  python -m resipsc.cli qc --input data/pbmc3k_raw.h5ad --batch-id B-001
  python -m resipsc.cli audit verify
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="resipsc")
    sub = parser.add_subparsers(dest="cmd", required=True)

    qc = sub.add_parser("qc", help="run QC on a file")
    qc.add_argument("--input", required=True)
    qc.add_argument("--batch-id", default="BATCH-000")
    qc.add_argument("--model", default="results/final_model.pkl")
    qc.add_argument("--out", default=None)

    verify = sub.add_parser("audit", help="audit trail utilities")
    verify.add_argument("action", choices=["verify", "export-csv"])
    verify.add_argument("--out", default="download/audit_export.csv")

    args = parser.parse_args(argv)

    if args.cmd == "qc":
        from resipsc.utils.io import load_pickle
        from scripts.qc_fast import run_qc  # reuse the universal QC runner

        model = load_pickle(args.model)
        report = run_qc(args.input, model, batch_id=args.batch_id)
        if args.out:
            from resipsc.utils.io import save_json

            save_json(report, args.out)
        print(json.dumps({"status": "ok", "decision": report.get("decision")}))
        return 0

    if args.cmd == "audit":
        from resipsc.compliance.audit import AuditTrail

        trail = AuditTrail()
        if args.action == "verify":
            print(json.dumps(trail.verify_chain(), indent=2))
        else:
            n = trail.export_csv(args.out)
            print(json.dumps({"status": "ok", "exported": n, "path": args.out}))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
