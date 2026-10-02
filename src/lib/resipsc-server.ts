/**
 * Shared server-side helpers for resipsc API routes.
 *
 * Implements the critical patterns from the build specification:
 *  - PROJECT_ROOT resolution that works in dev AND standalone builds (PART 3.2)
 *  - memory guard before spawning Python (PART 3.6)
 *  - DATABASE_URL stripped from the child environment (PART 3.1 — the
 *    anndata/pydantic-settings conflict; sitecustomize.py is the belt, this
 *    is the braces)
 *  - Python subprocess execution with last-line JSON parsing
 */

import { spawn } from "child_process";
import { existsSync, readFileSync } from "fs";
import { freemem } from "os";
import path from "path";

/** Resolve the project root: dev (cwd) first, then standalone fallbacks. */
export function projectRoot(): string {
  const candidates = [
    process.cwd(),
    path.resolve(process.cwd(), ".."),
    path.resolve(__dirname, "..", "..", "..", ".."),
    path.resolve(__dirname, "..", "..", ".."),
  ];
  for (const c of candidates) {
    if (c && existsSync(path.join(c, "results"))) return c;
  }
  // absolute last resort for this container
  if (existsSync("/home/z/my-project/results")) return "/home/z/my-project";
  return process.cwd();
}

export const PROJECT_ROOT = projectRoot();

/** Locate the Python interpreter that has the ML stack installed. */
export function pythonBin(): string {
  if (process.env.RESIPSC_PYTHON && existsSync(process.env.RESIPSC_PYTHON)) {
    return process.env.RESIPSC_PYTHON;
  }
  const candidates = [
    "/home/z/.venv/bin/python3",
    "/usr/bin/python3",
    "python3",
  ];
  for (const c of candidates) {
    if (c.includes("/") && existsSync(c)) return c;
  }
  return "python3";
}

export interface SpawnResult {
  code: number;
  stdout: string;
  stderr: string;
  ok: boolean;
}

/** Run a Python script, collecting output. Never throws. */
export function runPython(
  args: string[],
  timeoutMs = 300_000,
): Promise<SpawnResult> {
  return new Promise((resolve) => {
    const bin = pythonBin();
    // strip Prisma's DATABASE_URL for the child process (PART 3.1)
    const env: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) {
      if (k === "DATABASE_URL" || k === "DATABASE_URL_FILE") continue;
      if (typeof v === "string") env[k] = v;
    }
    env.PYTHONWARNINGS = "ignore";
    env.PYTHONUNBUFFERED = "1";

    const proc = spawn(bin, args, { cwd: PROJECT_ROOT, env });

    let stdout = "";
    let stderr = "";
    let done = false;
    const timer = setTimeout(() => {
      if (!done) {
        done = true;
        try {
          proc.kill("SIGKILL");
        } catch {
          /* already dead */
        }
      }
    }, timeoutMs);

    proc.stdout.on("data", (d: Buffer) => {
      stdout += d.toString();
      // keep memory bounded for huge accidental prints
      if (stdout.length > 20_000_000) stdout = stdout.slice(-10_000_000);
    });
    proc.stderr.on("data", (d: Buffer) => {
      stderr += d.toString();
      if (stderr.length > 2_000_000) stderr = stderr.slice(-1_000_000);
    });
    proc.on("error", (err) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ code: -1, stdout, stderr: `${stderr}\n${err}`, ok: false });
    });
    proc.on("close", (code) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ code: code ?? -1, stdout, stderr, ok: code === 0 });
    });
  });
}

/** Parse the LAST non-empty stdout line as JSON. Returns null on failure. */
export function parseLastJsonLine<T = unknown>(stdout: string): T | null {
  const lines = stdout.split("\n").map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    try {
      return JSON.parse(lines[i]) as T;
    } catch {
      // keep walking backwards
    }
  }
  return null;
}

/** Free RAM in MB. */
export function freeRamMb(): number {
  return freemem() / 1e6;
}

/** Insufficient-RAM response (PART 3.6 — 507 when < 400 MB free). */
export class LowMemoryError extends Error {
  constructor(public freeMb: number) {
    super(`Insufficient RAM: ${Math.round(freeMb)} MB free (< 400 MB required)`);
  }
}

export function assertMemory(): void {
  const free = freeRamMb();
  if (free < 400) throw new LowMemoryError(free);
}

/** Safe string coercion for PDF/report params. */
export function safeStr(v: unknown, maxLen = 300): string {
  if (typeof v === "string") return v.slice(0, maxLen);
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return "";
}

/** Join with the turbopackIgnore hint (PART 3.9). */
export function pj(...parts: string[]): string {
  return path.join(/*turbopackIgnore: true*/ ...parts);
}
