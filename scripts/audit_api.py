#!/usr/bin/env python3
"""audit_api.py — Part 11 audit trail query endpoint (Python side).

Usage:
  python scripts/audit_api.py [--entity-type T] [--entity-id I] [--action A]
                               [--from DATE] [--to DATE] [--limit N] [--export-csv PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity-type", default=None)
    ap.add_argument("--entity-id", default=None)
    ap.add_argument("--action", default=None)
    ap.add_argument("--from", dest="from_date", default=None)
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--export-csv", default=None)
    args = ap.parse_args()

    from resipsc.compliance.audit import AuditTrail

    trail = AuditTrail()

    if args.export_csv:
        n = trail.export_csv(args.export_csv)
        print(json.dumps({"status": "ok", "exported": n, "path": args.export_csv}))
        return 0

    events = trail.query(
        entity_type=args.entity_type,
        entity_id=args.entity_id,
        action=args.action,
        from_date=args.from_date,
        to_date=args.to_date,
        limit=args.limit,
    )
    chain = trail.verify_chain()
    print(json.dumps({
        "status": "ok",
        "n_events": len(events),
        "chain": chain,
        "events": events,
    }, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
