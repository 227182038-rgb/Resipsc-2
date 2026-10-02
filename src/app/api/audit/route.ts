import { NextRequest, NextResponse } from "next/server";
import path from "path";

import { PROJECT_ROOT, runPython } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/audit — 21 CFR Part 11 audit trail query.
 *
 * Query params: entity_type, entity_id, action, from (YYYY-MM-DD),
 * to (YYYY-MM-DD), limit, export_csv (path).
 * Response includes the recomputed hash-chain integrity check.
 */
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const args = [
      path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "audit_api.py"),
      "--limit",
      url.searchParams.get("limit") ?? "200",
    ];
    const passthrough: Array<[string, string]> = [
      ["entity_type", "--entity-type"],
      ["entity_id", "--entity-id"],
      ["action", "--action"],
      ["from", "--from"],
      ["to", "--to"],
    ];
    for (const [param, flag] of passthrough) {
      const v = url.searchParams.get(param);
      if (v && v.trim()) args.push(flag, v.trim().slice(0, 200));
    }
    const exportCsv = url.searchParams.get("export_csv");
    if (exportCsv) {
      const safe = exportCsv.replace(/[^\w./-]/g, "_").slice(0, 200);
      args.push("--export-csv", path.join(PROJECT_ROOT, safe));
    }

    const { ok, code, stdout, stderr } = await runPython(args, 120_000);
    const lines = stdout.trim().split("\n");
    const last = lines[lines.length - 1] || "{}";
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(last) as Record<string, unknown>;
    } catch {
      parsed = {};
    }
    if (!ok && parsed.status !== "ok") {
      return NextResponse.json(
        {
          status: "error",
          message: `audit query failed (exit ${code})`,
          detail: stderr.split("\n").slice(-6).join("\n").slice(0, 1500),
        },
        { status: 500 },
      );
    }
    return NextResponse.json(parsed);
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
