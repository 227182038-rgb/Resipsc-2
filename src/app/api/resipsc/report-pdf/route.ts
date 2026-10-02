import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "fs";
import path from "path";
import { tmpdir } from "os";

import { PROJECT_ROOT, pythonBin } from "@/lib/resipsc-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/resipsc/report-pdf?path=<json-or-plain>
 *
 * Renders the 14-page QC report PDF via scripts/render_qc_pdf.py and
 * streams it back. The `path` query parameter may be plain
 * (results/qc_reports/X.json) or JSON-encoded.
 */
export async function GET(req: NextRequest) {
  const tmpDir = mkdtempSync(path.join(tmpdir(), "resipsc-pdf-"));
  try {
    const url = new URL(req.url);
    const raw = url.searchParams.get("path") ?? "";

    // accept both plain and JSON-encoded path values
    let reportPath = raw;
    if (raw.startsWith("%22") || raw.startsWith('"') || raw.startsWith("%7B")) {
      try {
        const dec = decodeURIComponent(raw);
        const parsed = JSON.parse(dec) as unknown;
        if (typeof parsed === "string") reportPath = parsed;
      } catch {
        /* fall through with the raw value */
      }
    }
    if (!reportPath) {
      return NextResponse.json(
        { status: "error", message: "path query parameter is required" },
        { status: 400 },
      );
    }

    const abs = path.isAbsolute(reportPath)
      ? reportPath
      : path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, reportPath);
    if (!existsSync(abs)) {
      return NextResponse.json(
        { status: "error", message: `report not found: ${reportPath}` },
        { status: 404 },
      );
    }

    const outPdf = path.join(tmpDir, "report.pdf");
    const proc = await new Promise<{ code: number; stdout: string; stderr: string }>((resolve) => {
      const env: Record<string, string> = { PYTHONWARNINGS: "ignore", PYTHONUNBUFFERED: "1" };
      for (const [k, v] of Object.entries(process.env)) {
        if (k === "DATABASE_URL" || k === "DATABASE_URL_FILE") continue;
        if (typeof v === "string") env[k] = v;
      }
      const p = spawn(
        pythonBin(),
        [
          path.join(/*turbopackIgnore: true*/ PROJECT_ROOT, "scripts", "render_qc_pdf.py"),
          "--report",
          abs,
          "--out",
          outPdf,
        ],
        { cwd: PROJECT_ROOT, env },
      );
      let stdout = "";
      let stderr = "";
      p.stdout.on("data", (d: Buffer) => {
        stdout += d.toString();
      });
      p.stderr.on("data", (d: Buffer) => {
        stderr += d.toString();
      });
      const timer = setTimeout(() => p.kill("SIGKILL"), 120_000);
      p.on("error", (e) => {
        clearTimeout(timer);
        resolve({ code: -1, stdout, stderr: `${stderr}\n${e}` });
      });
      p.on("close", (code) => {
        clearTimeout(timer);
        resolve({ code: code ?? -1, stdout, stderr });
      });
    });

    if (proc.code !== 0 || !existsSync(outPdf)) {
      return NextResponse.json(
        {
          status: "error",
          message: "PDF rendering failed",
          detail: proc.stderr.split("\n").slice(-8).join("\n").slice(0, 2000),
        },
        { status: 500 },
      );
    }

    const bytes = readFileSync(outPdf);
    const batchHint = path.basename(abs).split("_")[0];
    return new NextResponse(new Uint8Array(bytes), {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Length": String(bytes.length),
        "Content-Disposition": `attachment; filename="resipsc_qc_report_${batchHint}.pdf"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    return NextResponse.json(
      { status: "error", message: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  } finally {
    try {
      rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      /* best effort */
    }
  }
}
