#!/usr/bin/env python3
"""build_pccp.py — write the PCCP template markdown (FDA Dec 2024 guidance)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from resipsc.compliance.pccp import build_pccp_template


def render_md(p: dict) -> str:
    lines = [
        f"# {p['title']}",
        "",
        f"**Model:** {p['model']}  ",
        f"**Guidance:** {p['guidance']}  ",
        f"**Retrain trigger:** {p['retrain_trigger']}",
        "",
        "## Section 1 — Description of Planned Changes",
        "",
    ]
    for c in p["section_1_description_of_changes"]["planned_changes"]:
        lines += [
            f"### {c['change_id']} — {c['component']}",
            "",
            f"- **Planned modification:** {c['planned_modification']}",
            f"- **Frequency:** {c['frequency']}",
            f"- **Risk:** {c['risk']}",
            "",
        ]
    lines += ["Out of scope:"] + [f"- {o}" for o in p["section_1_description_of_changes"]["out_of_scope"]]

    lines += [
        "",
        "## Section 2 — Modification Protocol",
        "",
        f"**Data requirements.** {p['section_2_modification_protocol']['data_requirements']}",
        "",
        "**Retraining procedure:**",
        "",
    ] + [f"{s}" for s in p["section_2_modification_protocol"]["retraining_procedure"]] + [
        "",
        "**Acceptance criteria:**",
        "",
        f"| Criterion | Threshold |",
        f"|-----------|-----------|",
    ] + [f"| {k} | {v} |" for k, v in p["section_2_modification_protocol"]["acceptance_criteria"].items()] + [
        "",
        f"**Verification.** {p['section_2_modification_protocol']['verification']}",
        "",
        "## Section 3 — Impact Assessment",
        "",
        f"**Benefit-risk.** {p['section_3_impact_assessment']['benefit_risk']}",
        "",
        f"**Post-market monitoring.** {p['section_3_impact_assessment']['post_market_monitoring']}",
        "",
        f"**Rollback plan.** {p['section_3_impact_assessment']['rollback_plan']}",
        "",
        f"**Records.** {p['records']}",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = build_pccp_template()
    os.makedirs("paper", exist_ok=True)
    out = "paper/pccp_template.md"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render_md(p))
    print(json.dumps({"status": "ok", "path": out, "changes": len(p["section_1_description_of_changes"]["planned_changes"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
