import { NextRequest, NextResponse } from "next/server";
import { mkdirSync, readdirSync, rmSync, statSync, writeFileSync, existsSync } from "fs";
import path from "path";

import { PROJECT_ROOT } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UPLOAD_ROOT = () =>
  path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "data", "uploads");

/**
 * POST /api/resipsc/chunk — receive ONE 1 MB chunk of a file.
 *
 * Chunked upload protocol (PART 3.3):
 *  - uploads are SEQUENTIAL on the client (MAX_PARALLEL = 1) to avoid the
 *    race condition where parallel chunk 0 cleanup deletes sibling chunks;
 *  - each chunk is stored as data/uploads/<uploadId>/part_<index>.bin;
 *  - NEVER unlink on chunk 0 — cleanup only happens for sessions older
 *    than 2 hours (stale session sweep below);
 *  - body is raw octet-stream; query carries uploadId/index/totalChunks.
 */
export async function POST(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const uploadId = (url.searchParams.get("uploadId") ?? "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 64);
    const index = Number(url.searchParams.get("index") ?? "-1");
    const totalChunks = Number(url.searchParams.get("totalChunks") ?? "0");

    if (!uploadId || !Number.isInteger(index) || index < 0) {
      return NextResponse.json(
        { status: "error", message: "uploadId and index query params are required" },
        { status: 400 },
      );
    }

    const sessionDir = path.join(UPLOAD_ROOT(), uploadId);
    mkdirSync(sessionDir, { recursive: true });

    // stale session cleanup: remove dirs untouched for 2 hours (never our own)
    try {
      const now = Date.now();
      for (const entry of readdirSync(UPLOAD_ROOT())) {
        const d = path.join(UPLOAD_ROOT(), entry);
        try {
          const st = statSync(d);
          if (st.isDirectory() && now - st.mtimeMs > 2 * 3600 * 1000) {
            rmSync(d, { recursive: true, force: true });
          }
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* uploads root may not exist yet */
    }

    const buf = Buffer.from(await req.arrayBuffer());
    if (buf.length === 0) {
      return NextResponse.json({ status: "error", message: "empty chunk" }, { status: 400 });
    }
    if (buf.length > 16 * 1024 * 1024) {
      return NextResponse.json(
        { status: "error", message: `chunk too large (${buf.length} bytes > 16 MB)` },
        { status: 413 },
      );
    }

    const partPath = path.join(sessionDir, `part_${String(index).padStart(6, "0")}.bin`);
    writeFileSync(partPath, buf);

    // report progress (received parts / declared total)
    let received = 0;
    try {
      received = readdirSync(sessionDir).filter((f) => f.endsWith(".bin")).length;
    } catch {
      received = 1;
    }

    return NextResponse.json({
      status: "ok",
      uploadId,
      index,
      bytes: buf.length,
      received_chunks: received,
      total_chunks: totalChunks || null,
      part_path: `data/uploads/${uploadId}/part_${String(index).padStart(6, "0")}.bin`,
    });
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}

/** GET: list incomplete upload sessions (debug/monitoring). */
export async function GET() {
  try {
    const root = UPLOAD_ROOT();
    if (!existsSync(root)) {
      return NextResponse.json({ status: "ok", sessions: [] });
    }
    const sessions = readdirSync(root)
      .filter((d) => statSync(path.join(root, d)).isDirectory())
      .map((d) => {
        const dir = path.join(root, d);
        const parts = readdirSync(dir).filter((f) => f.endsWith(".bin"));
        const bytes = parts.reduce((s, f) => s + statSync(path.join(dir, f)).size, 0);
        return { uploadId: d, parts: parts.length, bytes, modified: statSync(dir).mtime.toISOString() };
      });
    return NextResponse.json({ status: "ok", sessions });
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
