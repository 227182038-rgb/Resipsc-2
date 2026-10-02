import { NextRequest, NextResponse } from "next/server";
import path from "path";

import { PROJECT_ROOT, runPython } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/comparability — ICH Q5E comparability between two model versions.
 *
 * Body: { old?, new?, trainCandidate? }
 * Defaults: old = results/final_model.pkl, new = freshly trained candidate
 * (seed 123) on the frozen golden corpus — a realistic promotion gate demo.
 */
export async function POST(req: NextRequest) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      old?: string;
      new?: string;
      trainCandidate?: boolean;
    };
    const args = [
      path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "comparability_api.py"),
    ];
    if (body.old) {
      const abs = path.isAbsolute(body.old)
        ? body.old
        : path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, body.old);
      args.push("--old", abs);
    }
    if (body.new) {
      const abs = path.isAbsolute(body.new)
        ? body.new
        : path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, body.new);
      args.push("--new", abs);
    }
    if (body.trainCandidate !== false) {
      args.push("--train-candidate");
    }

    // candidate training can take up to ~2 minutes on 2 cores
    const { ok, code, stdout, stderr } = await runPython(args, 420_000);
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
          message: (parsed.message as string) ?? `comparability failed (exit ${code})`,
          detail: stderr.split("\n").slice(-8).join("\n").slice(0, 2000),
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
