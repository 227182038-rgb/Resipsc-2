import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  statSync,
} from "fs";
import path from "path";
import { freemem } from "os";

import { PROJECT_ROOT, parseLastJsonLine, pythonBin } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/resipsc/assemble — stitch sequential chunks + run QC.
 *
 * Body: { uploadId, fileName?, totalChunks?, batchId? }
 * Parts are stitched strictly in part_ index order, size-validated, written
 * to the final file, then the standard QC pipeline runs on the assembly.
 * The session directory is removed only after a successful stitch+QC —
 * and never in a way that can race a concurrent chunk write (uploads are
 * sequential by protocol).
 */
export async function POST(req: NextRequest) {
  try {
    // memory guard before spawning Python (PART 3.6)
    const freeMb = freemem() / 1e6;
    if (freeMb < 400) {
      return NextResponse.json(
        { status: "error", message: `Insufficient RAM: ${Math.round(freeMb)} MB free (< 400 MB)` },
        { status: 507 },
      );
    }

    const body = (await req.json().catch(() => ({}))) as {
      uploadId?: string;
      fileName?: string;
      totalChunks?: number;
      batchId?: string;
    };
    const uploadId = (body.uploadId ?? "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 64);
    const batchId = (body.batchId ?? "").trim() || `ASSEMBLED-${uploadId.slice(0, 10).toUpperCase()}`;
    if (!uploadId) {
      return NextResponse.json({ status: "error", message: "uploadId is required" }, { status: 400 });
    }

    const sessionDir = path.join(
      /*turbopackIgnore: true*/ PROJECT_ROOT,
      "data",
      "uploads",
      uploadId,
    );
    if (!existsSync(sessionDir)) {
      return NextResponse.json(
        { status: "error", message: `no upload session found for ${uploadId}` },
        { status: 404 },
      );
    }

    // ---- stitch parts in index order --------------------------------------
    const parts = readdirSync(sessionDir)
      .filter((f) => /^part_\d{6}\.bin$/.test(f))
      .sort();
    if (parts.length === 0) {
      return NextResponse.json(
        { status: "error", message: "no chunks received for this uploadId" },
        { status: 400 },
      );
    }
    if (body.totalChunks && parts.length < body.totalChunks) {
      return NextResponse.json(
        {
          status: "error",
          message: `incomplete upload: ${parts.length}/${body.totalChunks} chunks`,
        },
        { status: 400 },
      );
    }

    const totalBytes = parts.reduce(
      (s, f) => s + statSync(path.join(sessionDir, f)).size,
      0,
    );
    if (totalBytes === 0) {
      return NextResponse.json({ status: "error", message: "assembled file is empty" }, { status: 400 });
    }

    // memory guard: the sequential stitch below needs ~1 chunk of RAM, but the
    // QC subprocess needs headroom — require 400 MB + 0.8x file size free
    const freeMbForQc = freemem() / 1e6;
    const neededMb = Math.max(400, (totalBytes / 1e6) * 0.8);
    if (freeMbForQc < neededMb) {
      return NextResponse.json(
        {
          status: "error",
          message: `Insufficient RAM for QC of a ${(totalBytes / 1e6).toFixed(0)} MB file: ${Math.round(freeMbForQc)} MB free (need ${Math.round(neededMb)})`,
        },
        { status: 507 },
      );
    }

    const safeName = (body.fileName ?? "upload.h5ad").replace(/[^\w.-]/g, "_").slice(-80) || "upload.h5ad";
    const outDir = path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "data", "uploads", "assembled");
    mkdirSync(outDir, { recursive: true });
    const finalPath = path.join(outDir, `${uploadId}_${safeName}`);

    // ---- append parts sequentially (RAM bounded by ONE chunk, ~1 MB) ----
    // Each part is at most 2 MB, so per-iteration memory is trivially small
    // regardless of total file size — this is the fix for the 557 MB OOM.
    const fsp = await import("fs/promises");
    let written = 0;
    try {
      for (const part of parts) {
        const buf = await fsp.readFile(path.join(sessionDir, part));
        await fsp.appendFile(finalPath, buf);
        written += buf.length;
      }
    } catch (e) {
      return NextResponse.json(
        { status: "error", message: `stitch failed: ${e instanceof Error ? e.message : String(e)}` },
        { status: 500 },
      );
    }
    if (written !== totalBytes) {
      return NextResponse.json(
        { status: "error", message: `size validation failed during stitch (${written} vs ${totalBytes} bytes)` },
        { status: 500 },
      );
    }

    // ---- run QC on the assembly -------------------------------------------
    const args = [
      path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "qc_fast.py"),
      "--input",
      finalPath,
      "--batch-id",
      batchId,
      "--model",
      path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "results", "final_model.pkl"),
    ];

    const result = await new Promise<{ status: number; body: unknown }>((resolve) => {
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
      const timer = setTimeout(() => proc.kill("SIGKILL"), 420_000);
      proc.on("error", (e) => {
        clearTimeout(timer);
        resolve({ status: 500, body: { status: "error", message: `spawn failed: ${e}` } });
      });
      proc.on("close", (code) => {
        clearTimeout(timer);
        const parsed = parseLastJsonLine<Record<string, unknown>>(out);
        if (parsed && (parsed.status === "ok" || parsed.status === "error")) {
          resolve({
            status: parsed.status === "ok" ? 200 : 400,
            body: parsed,
          });
        } else {
          resolve({
            status: 500,
            body: {
              status: "error",
              message: `QC on assembled file failed (exit ${code})`,
              detail: errOut.split("\n").slice(-8).join("\n").slice(0, 2000),
            },
          });
        }
      });
    });

    // graceful cleanup of the chunk session AFTER the pipeline has read the file
    try {
      rmSync(sessionDir, { recursive: true, force: true });
    } catch {
      /* best-effort; the 2h stale sweep in the chunk route will catch it */
    }

    return NextResponse.json(
      {
        ...(result.body as Record<string, unknown>),
        assembled_file: `data/uploads/assembled/${uploadId}_${safeName}`,
        assembled_bytes: totalBytes,
        chunks_stitched: parts.length,
      },
      { status: result.status },
    );
  } catch (err) {
    return NextResponse.json(
      {
        status: "error",
        message: err instanceof Error ? err.message : String(err),
        hint: "If the upload contained a partial JSON body, the file may be corrupt — re-upload.",
      },
      { status: 500 },
    );
  }
}
