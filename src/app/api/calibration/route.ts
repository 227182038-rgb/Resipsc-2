import { NextRequest, NextResponse } from "next/server";
import { existsSync } from "fs";
import path from "path";

import { PROJECT_ROOT, runPython } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/calibration — drift monitoring status (KL/JS/Wasserstein/KS).
 * POST /api/calibration { filePath, batchId } — run a drift check on a file.
 */
export async function GET() {
  const { ok, code, stdout, stderr } = await runPython(
    [path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "calibration_api.py"), "--status"],
    120_000,
  );
  if (!ok) {
    return NextResponse.json(
      {
        status: "error",
        message: `calibration status failed (exit ${code})`,
        detail: stderr.split("\n").slice(-6).join("\n").slice(0, 1500),
      },
      { status: 500 },
    );
  }
  const lines = stdout.trim().split("\n");
  const last = lines[lines.length - 1] || "{}";
  try {
    const parsed = JSON.parse(last) as unknown;
    return NextResponse.json(parsed);
  } catch {
    return NextResponse.json({ status: "error", message: "bad calibration payload" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      filePath?: string;
      batchId?: string;
    };
    const filePath = (body.filePath ?? "").trim();
    const batchId = (body.batchId ?? "").trim() || "CALIB-CHECK";
    if (!filePath) {
      return NextResponse.json({ status: "error", message: "filePath is required" }, { status: 400 });
    }
    const abs = path.isAbsolute(filePath)
      ? filePath
      : path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, filePath);
    if (!existsSync(abs)) {
      return NextResponse.json(
        { status: "error", message: `file not found: ${filePath}` },
        { status: 404 },
      );
    }

    const { ok, stdout, stderr } = await runPython(
      [
        path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "calibration_api.py"),
        "--check",
        abs,
        "--batch-id",
        batchId,
      ],
      240_000,
    );
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
          message: (parsed.message as string) ?? `calibration check failed`,
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
