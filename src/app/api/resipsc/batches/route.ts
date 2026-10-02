import { NextResponse } from "next/server";
import { existsSync, readdirSync, readFileSync, statSync } from "fs";
import path from "path";

import { PROJECT_ROOT } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/resipsc/batches — list previous QC reports (newest first). */
export async function GET() {
  try {
    const dir = path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "results", "qc_reports");
    if (!existsSync(dir)) {
      return NextResponse.json({ status: "ok", batches: [], n: 0 });
    }
    const files = readdirSync(dir)
      .filter((f) => f.endsWith(".json"))
      .map((f) => {
        const full = path.join(dir, f);
        const st = statSync(full);
        return { f, full, mtime: st.mtimeMs };
      })
      .sort((a, b) => b.mtime - a.mtime);

    const batches = files.slice(0, 50).map(({ f, full, mtime }) => {
      try {
        const r = JSON.parse(readFileSync(full, "utf-8")) as Record<string, unknown>;
        const rm = (r.report_metadata ?? {}) as Record<string, unknown>;
        return {
          file: `results/qc_reports/${f}`,
          batch_id: (r.batch_id as string) ?? (rm.batch_id as string) ?? f.split("_")[0],
          decision: r.decision ?? "UNKNOWN",
          risk_tier: ((r.risk_tier ?? {}) as Record<string, unknown>).tier ?? null,
          generated_at_utc: rm.generated_at_utc ?? new Date(mtime).toISOString(),
          n_cells: r.n_cells ?? null,
          input_total_cells: r.input_total_cells ?? null,
          estimated_psc_fraction: r.estimated_psc_fraction ?? null,
          estimated_psc_count: r.estimated_psc_count ?? null,
          biomarker_model_agreement: r.biomarker_model_agreement ?? null,
          input_file: r.input_file ?? null,
          report_id: rm.report_id ?? null,
          runtime_seconds: r.runtime_seconds ?? null,
          mtime,
        };
      } catch {
        return null;
      }
    });

    const valid = batches.filter(Boolean) as NonNullable<(typeof batches)[number]>[];
    return NextResponse.json({ status: "ok", batches: valid, n: valid.length });
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
