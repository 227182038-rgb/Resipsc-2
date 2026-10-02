#!/usr/bin/env python3
"""build_fmea.py — write the FMEA worksheet markdown (ICH Q9)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resipsc.compliance.fmea import build_fmea_worksheet


def render_md(fmea: dict) -> str:
    lines = [
        f"# {fmea['title']}",
        "",
        f"**Standard:** {fmea['standard']}  ",
        f"**Team:** {fmea['team']}  ",
        f"**Scale:** {fmea['scale']}  ",
        f"**Review cycle:** {fmea['review_cycle']}",
        "",
        "## Risk summary",
        "",
        f"- Failure modes: **{fmea['summary']['n_failure_modes']}**",
        f"- HIGH risk (RPN >= 150): **{fmea['summary']['high_risk']}**",
        f"- MEDIUM risk (60 <= RPN < 150): **{fmea['summary']['medium_risk']}**",
        f"- LOW risk (RPN < 60): **{fmea['summary']['low_risk']}**",
        f"- Maximum RPN: **{fmea['summary']['max_rpn']}**",
        "",
        "## Worksheet",
        "",
        "| ID | Component | Failure mode | Effect | S | O | D | RPN | Class | Controls | Mitigation |",
        "|----|-----------|-------------|--------|---|---|---|-----|-------|----------|-------------|",
    ]
    for r in fmea["rows"]:
        lines.append(
            f"| {r['id']} | {r['component']} | {r['failure_mode']} | {r['effect']} | "
            f"{r['severity']} | {r['occurrence']} | {r['detection']} | {r['rpn']} | "
            f"**{r['risk_class']}** | {r['controls']} | {r['mitigation']} |"
        )
    lines += [
        "",
        "## Linked documents",
        "",
    ] + [f"- {d}" for d in fmea["linked_documents"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    fmea = build_fmea_worksheet()
    os.makedirs("paper", exist_ok=True)
    out = "paper/fmea_worksheet.md"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_md(fmea))
    print(json.dumps({"status": "ok", "path": out,
                      "rows": fmea["summary"]["n_failure_modes"],
                      "high": fmea["summary"]["high_risk"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
