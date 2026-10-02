import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { existsSync, mkdirSync, writeFileSync, statSync } from "fs";
import path from "path";
import { freemem } from "os";

import { PROJECT_ROOT, parseLastJsonLine, pythonBin } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function readJsonSafe(p: string): unknown | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const fs = require("fs") as typeof import("fs");
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function modelStatus() {
  try {
    const p = path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "results", "final_model.pkl");
    if (!existsSync(p)) return { ready: false, reason: "results/final_model.pkl not found" };
    const st = statSync(p);
    return {
      ready: true,
      path: "results/final_model.pkl",
      size_mb: Math.round(st.size / 1e5) / 10,
      modified: st.mtime.toISOString(),
      version: "resipsc-ensemble-2.0.0",
    };
  } catch {
    return { ready: false, reason: "stat failed" };
  }
}

/** GET: benchmark results + model status for the dashboard. */
export async function GET() {
  try {
    const R = (f: string) =>
      readJsonSafe(path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "results", f));

    const multisite = R("multisite_results.json");
    const spikein = R("spikein_results.json");
    const lineage = R("lineage_results.json");
    const gaps = R("gap_fix_summary.json");
    const card = R("model_card.json");

    let registry: Array<Record<string, unknown>> = [];
    try {
      const csv = (await import("fs")).readFileSync(
        path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "results", "dataset_registry.csv"),
        "utf-8",
      );
      const lines = csv.trim().split("\n");
      const header = lines[0].split(",");
      registry = lines.slice(1).map((line) => {
        const cells = line.split(",");
        const row: Record<string, unknown> = {};
        header.forEach((h, i) => (row[h] = cells[i] ?? ""));
        return row;
      });
    } catch {
      registry = [];
    }

    const trainingCorpus = (card as Record<string, Record<string, unknown>> | null)
      ?.training_data_summary;

    return NextResponse.json({
      status: "ok",
      software: "resipsc v2.0.0",
      model: modelStatus(),
      benchmarks: { multisite, spikein, lineage, gap_summary: gaps },
      model_card: card,
      dataset_registry: registry,
      training: trainingCorpus ?? null,
    });
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}

/** Spawn the QC python and parse its report. */
async function runQc(
  inputPath: string,
  batchId: string,
): Promise<{ status: number; body: unknown }> {
  const args = [
    path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "qc_fast.py"),
    "--input",
    inputPath,
    "--batch-id",
    batchId,
    "--model",
    path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "results", "final_model.pkl"),
  ];
  return await new Promise((resolve) => {
    const env: Record<string, string> = { PYTHONWARNINGS: "ignore", PYTHONUNBUFFERED: "1" };
    for (const [k, v] of Object.entries(process.env)) {
      if (k === "DATABASE_URL" || k === "DATABASE_URL_FILE") continue;
      if (typeof v === "string") env[k] = v;
    }
    const proc = spawn(pythonBin(), args, { cwd: PROJECT_ROOT, env });
    let out = "";
    let errOut = "";
    proc.stdout.on("data", (d: Buffer) => {
      out += d.toString();
    });
    proc.stderr.on("data", (d: Buffer) => {
      errOut += d.toString();
    });
    const timer = setTimeout(() => proc.kill("SIGKILL"), 300_000);
    proc.on("error", (e) => {
      clearTimeout(timer);
      resolve({ status: 500, body: { status: "error", message: `spawn failed: ${e}` } });
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      const parsed = parseLastJsonLine<Record<string, unknown>>(out);
      if (parsed && (parsed.status === "ok" || parsed.status === "error")) {
        if (parsed.status === "error") {
          resolve({ status: (parsed.exit_code as number) === 2 ? 507 : 400, body: parsed });
        } else {
          resolve({ status: 200, body: parsed });
        }
      } else {
        resolve({
          status: 500,
          body: {
            status: "error",
            message: `QC pipeline failed (exit ${code})`,
            detail: errOut.split("\n").slice(-8).join("\n").slice(0, 2000),
          },
        });
      }
    });
  });
}

/** POST: file-path QC (JSON) or direct upload QC (multipart, < 5 MB). */
export async function POST(req: NextRequest) {
  try {
    const freeMb = freemem() / 1e6;
    if (freeMb < 400) {
      return NextResponse.json(
        { status: "error", message: `Insufficient RAM: ${Math.round(freeMb)} MB free (< 400 MB)` },
        { status: 507 },
      );
    }

    const contentType = req.headers.get("content-type") ?? "";

    // ---- Method 1: JSON body with a server-side file path ---------------
    if (contentType.includes("application/json")) {
      const body = (await req.json().catch(() => ({}))) as {
        filePath?: string;
        batchId?: string;
      };
      const filePath = (body.filePath ?? "").trim();
      const batchId = (body.batchId ?? "").trim() || "BATCH-000";
      if (!filePath) {
        return NextResponse.json(
          { status: "error", message: "filePath is required" },
          { status: 400 },
        );
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
      const { status, body: out } = await runQc(abs, batchId);
      return NextResponse.json(out, { status });
    }

    // ---- Method 2: direct multipart upload (< 5 MB) ----------------------
    if (contentType.includes("multipart/form-data")) {
      const form = await req.formData();
      const file = form.get("file");
      const batchId = String(form.get("batchId") ?? "").trim() || "BATCH-UPLOAD";
      if (!(file instanceof File)) {
        return NextResponse.json(
          { status: "error", message: "file field is required" },
          { status: 400 },
        );
      }
      if (file.size > 5 * 1024 * 1024) {
        return NextResponse.json(
          {
            status: "error",
            message: `File too large for direct upload (${(file.size / 1e6).toFixed(1)} MB > 5 MB). Use chunked upload.`,
          },
          { status: 413 },
        );
      }
      const uploadDir = path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "data", "uploads");
      mkdirSync(uploadDir, { recursive: true });
      const safeName = (file.name || "upload.h5ad").replace(/[^\w.-]/g, "_").slice(-80);
      const dest = path.join(uploadDir, `direct_${Date.now()}_${safeName}`);
      const buf = Buffer.from(await file.arrayBuffer());
      writeFileSync(dest, buf);
      const { status, body: out } = await runQc(dest, batchId);
      return NextResponse.json(out, { status });
    }

    return NextResponse.json(
      { status: "error", message: "unsupported content type (use JSON or multipart)" },
      { status: 400 },
    );
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
