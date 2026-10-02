"use client";

/**
 * resipsc v2.0 — five-tab QC dashboard.
 *
 * Tabs: Benchmark · Sensitivity · QC Report · Datasets · Calibration
 *
 * Upload system (all three methods, PART 5.1):
 *   1. server-side file path (quick-select buttons)
 *   2. direct multipart POST (< 5 MB)
 *   3. sequential 1 MB chunked upload with assembly (MAX_PARALLEL = 1 to
 *      avoid the write race; 3 retries with exponential backoff)
 *
 * Honest-labelling banner reflects the real training corpus.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Beaker,
  BrainCircuit,
  Calendar,
  CheckCircle2,
  Database,
  FileCheck2,
  FileUp,
  FlaskConical,
  Gauge,
  Loader2,
  Microscope,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ElevatedQcReport,
  intg,
  num,
  pct,
  type QcReport,
} from "./elevated-qc-report";

type AnyRec = Record<string, unknown>;

function rec(v: unknown): AnyRec {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as AnyRec) : {};
}
function arr(v: unknown): AnyRec[] {
  return Array.isArray(v) ? (v as AnyRec[]) : [];
}
function sstr(v: unknown, max = 200): string {
  if (typeof v === "string") return v.slice(0, max);
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return "";
}

/* ================================================================== */
/* main page                                                            */
/* ================================================================== */

export default function Home() {
  const [api, setApi] = useState<AnyRec | null>(null);
  const [apiErr, setApiErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [batchId, setBatchId] = useState("BATCH-001");
  const [report, setReport] = useState<QcReport | null>(null);
  const [qcBusy, setQcBusy] = useState<string | null>(null);
  const [qcErr, setQcErr] = useState<string | null>(null);
  const [upload, setUpload] = useState<{
    phase: string;
    bytes: number;
    total: number;
    chunk: number;
    chunks: number;
  } | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [comparability, setComparability] = useState<AnyRec | null>(null);
  const [compBusy, setCompBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const loadBenchmarks = useCallback(async () => {
    setLoading(true);
    setApiErr(null);
    try {
      const res = await fetch("/api/resipsc", { cache: "no-store" });
      const json = (await res.json()) as AnyRec;
      if (json.status !== "ok") throw new Error(sstr(json.message, 300) || "API error");
      setApi(json);
    } catch (e) {
      setApiErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBenchmarks();
  }, [loadBenchmarks]);

  /* ------------------- QC: Method 1 (file path) ------------------- */
  const runQcOnPath = useCallback(
    async (filePath: string, id?: string) => {
      setQcBusy("Running QC on server file…");
      setQcErr(null);
      setReport(null);
      try {
        const res = await fetch("/api/resipsc", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filePath, batchId: id || batchId || "BATCH-001" }),
        });
        const json = (await res.json()) as AnyRec;
        if (!res.ok || json.status !== "ok") {
          throw new Error(sstr(json.message, 400) || `QC failed (HTTP ${res.status})`);
        }
        setReport(json as QcReport);
        setBatchId(sstr(json.batch_id, 40) || batchId);
      } catch (e) {
        setQcErr(e instanceof Error ? e.message : String(e));
      } finally {
        setQcBusy(null);
      }
    },
    [batchId],
  );

  /* ------------------- QC: Methods 2 & 3 (file) ------------------- */
  const runQcOnFile = useCallback(
    async (file: File, id?: string) => {
      const useBatchId = id || batchId || "BATCH-UPLOAD";
      setQcErr(null);
      setReport(null);

      if (file.size <= 5 * 1024 * 1024) {
        // ---- Method 2: direct multipart upload --------------------
        setQcBusy(`Uploading ${file.name} (${(file.size / 1e6).toFixed(2)} MB) directly…`);
        try {
          const form = new FormData();
          form.append("file", file);
          form.append("batchId", useBatchId);
          const res = await fetch("/api/resipsc", { method: "POST", body: form });
          const json = (await res.json()) as AnyRec;
          if (!res.ok || json.status !== "ok") {
            // fall back to chunked upload if direct fails (spec 5.1)
            await chunkedUpload(file, useBatchId);
            return;
          }
          setReport(json as QcReport);
        } catch {
          // network hiccup — retry once via chunked path
          await chunkedUpload(file, useBatchId);
        } finally {
          setQcBusy(null);
        }
      } else {
        // ---- Method 3: sequential chunked upload --------------------
        await chunkedUpload(file, useBatchId);
      }
    },
    [batchId],
  );

  const chunkedUpload = useCallback(
    async (file: File, useBatchId: string) => {
      const CHUNK = 1024 * 1024; // 1 MB
      const totalChunks = Math.ceil(file.size / CHUNK);
      const uploadId = `up_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

      setQcBusy("Preparing chunked upload…");
      setUpload({ phase: "uploading", bytes: 0, total: file.size, chunk: 0, chunks: totalChunks });

      try {
        let uploadedBytes = 0;
        for (let i = 0; i < totalChunks; i++) {
          const blob = file.slice(i * CHUNK, Math.min((i + 1) * CHUNK, file.size));
          const buf = await blob.arrayBuffer();

          // 3 retries per chunk with exponential backoff (1s, 2s, 3s)
          let ok = false;
          let lastErr = "";
          for (let attempt = 0; attempt < 3 && !ok; attempt++) {
            try {
              const res = await fetch(
                `/api/resipsc/chunk?uploadId=${encodeURIComponent(uploadId)}&index=${i}&totalChunks=${totalChunks}`,
                { method: "POST", body: buf },
              );
              const json = (await res.json()) as AnyRec;
              if (!res.ok || json.status !== "ok") throw new Error(sstr(json.message, 200) || `chunk ${i} failed`);
              ok = true;
            } catch (e) {
              lastErr = e instanceof Error ? e.message : String(e);
              if (attempt < 2) {
                await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
              }
            }
          }
          if (!ok) throw new Error(`chunk ${i + 1}/${totalChunks} failed after 3 retries: ${lastErr}`);

          uploadedBytes += blob.size;
          setUpload({
            phase: "uploading",
            bytes: uploadedBytes,
            total: file.size,
            chunk: i + 1,
            chunks: totalChunks,
          });
        }

        // ---- assemble + QC --------------------------------------
        setQcBusy("Assembling chunks and running QC…");
        setUpload((u) => (u ? { ...u, phase: "analysing" } : u));
        const res = await fetch("/api/resipsc/assemble", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            uploadId,
            fileName: file.name,
            totalChunks,
            batchId: useBatchId,
          }),
        });
        const json = (await res.json()) as AnyRec;
        if (!res.ok || json.status !== "ok") {
          throw new Error(sstr(json.message, 400) || `assembly failed (HTTP ${res.status})`);
        }
        setReport(json as QcReport);
      } catch (e) {
        setQcErr(e instanceof Error ? e.message : String(e));
      } finally {
        setQcBusy(null);
        setUpload(null);
      }
    },
    [],
  );

  /* ------------------- PDF download ------------------- */
  const downloadPdf = useCallback(async () => {
    if (!report) return;
    const saved = sstr((report as AnyRec).saved_report_path, 300);
    if (!saved) return;
    setPdfBusy(true);
    try {
      const res = await fetch(
        `/api/resipsc/report-pdf?path=${encodeURIComponent(JSON.stringify(saved))}`,
      );
      if (!res.ok) {
        const j = (await res.json().catch(() => ({}))) as AnyRec;
        throw new Error(sstr(j.message, 300) || `PDF failed (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `resipsc_qc_report_${sstr((report as AnyRec).batch_id, 40) || "batch"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setQcErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPdfBusy(false);
    }
  }, [report]);

  /* ------------------- comparability ------------------- */
  const runComparability = useCallback(async () => {
    setCompBusy(true);
    try {
      const res = await fetch("/api/comparability", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trainCandidate: true }),
      });
      const json = (await res.json()) as AnyRec;
      setComparability(rec(json.comparison));
    } catch (e) {
      setQcErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCompBusy(false);
    }
  }, []);

  /* ------------------- derived benchmark data ------------------- */
  const benchmarks = rec(api?.benchmarks);
  const multisite = rec(benchmarks.multisite);
  const spikein = rec(benchmarks.spikein);
  const lineage = rec(benchmarks.lineage);
  const gapSummary = rec(benchmarks.gap_summary);
  const modelStatus = rec(api?.model);
  const registry = arr(api?.dataset_registry);
  const training = rec(api?.training);
  const card = rec(api?.model_card);

  const msSummary = arr(multisite.summary);
  const msFolds = arr(multisite.per_fold);
  const spAgg = arr(spikein.aggregated);
  const linRows = arr(lineage.per_lineage);
  const gapRows = arr(gapSummary.gaps);
  const countries = arr(multisite.countries).map((c) => sstr(c, 40)).filter(Boolean);

  const trainingLabel =
    sstr(training.corpus, 200) || "hybrid (synthetic multi-site + real pbmc3k)";

  return (
    <main className="min-h-screen bg-slate-50 pb-16">
      {/* ================= header ================= */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-5 md:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal-800 text-white shadow">
                <BrainCircuit className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-xl font-black tracking-tight text-slate-900">
                  resipsc <span className="text-teal-700">v2.0</span>
                </h1>
                <p className="text-xs text-slate-500">
                  Residual pluripotent stem cell detection for cell therapy QC · scRNA-seq
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {modelStatus.ready ? (
                <Badge className="border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-50">
                  <ShieldCheck className="mr-1 h-3.5 w-3.5" /> model ready · {sstr(modelStatus.size_mb, 8)} MB
                </Badge>
              ) : (
                <Badge variant="outline" className="border-amber-300 text-amber-700">
                  model not trained
                </Badge>
              )}
              <Badge variant="outline" className="border-teal-300 text-teal-800">
                21 CFR Part 11 audit trail
              </Badge>
              <Button size="sm" variant="outline" onClick={() => void loadBenchmarks()} className="border-slate-300">
                <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* ================= honest labelling banner (5.5) ================= */}
      <div className="border-b border-amber-200 bg-amber-50">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2 px-4 py-2.5 text-xs text-amber-900 md:px-8">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>
            <strong>Hybrid-trained model</strong> — synthetic multi-site corpus + real pbmc3k with cross-batch
            noise ({trainingLabel}). Research Use Only — NOT FDA-cleared. Benchmarks reflect simulated
            manufacturing data; wet-lab validation is outstanding (see Datasets tab).
          </span>
        </div>
      </div>

      {apiErr && (
        <div className="mx-auto mt-3 max-w-7xl rounded-md border border-rose-300 bg-rose-50 px-4 py-2 text-sm text-rose-800">
          API error: {apiErr} — ensure the Python model pipeline is trained (results/final_model.pkl).
        </div>
      )}

      {/* ================= tabs ================= */}
      <div className="mx-auto max-w-7xl px-4 pt-5 md:px-8">
        <Tabs defaultValue="benchmark" className="w-full">
          <TabsList className="mb-4 h-auto flex-wrap justify-start gap-1 bg-slate-100 p-1">
            <TabsTrigger value="benchmark" className="gap-1.5 px-3 py-1.5 text-xs data-[state=active]:bg-white">
              <BarChart3 className="h-3.5 w-3.5" /> Benchmark
            </TabsTrigger>
            <TabsTrigger value="sensitivity" className="gap-1.5 px-3 py-1.5 text-xs data-[state=active]:bg-white">
              <FlaskConical className="h-3.5 w-3.5" /> Sensitivity
            </TabsTrigger>
            <TabsTrigger value="qc" className="gap-1.5 px-3 py-1.5 text-xs data-[state=active]:bg-white">
              <FileCheck2 className="h-3.5 w-3.5" /> QC Report
            </TabsTrigger>
            <TabsTrigger value="datasets" className="gap-1.5 px-3 py-1.5 text-xs data-[state=active]:bg-white">
              <Database className="h-3.5 w-3.5" /> Datasets
            </TabsTrigger>
            <TabsTrigger value="calibration" className="gap-1.5 px-3 py-1.5 text-xs data-[state=active]:bg-white">
              <Gauge className="h-3.5 w-3.5" /> Calibration
            </TabsTrigger>
          </TabsList>

          {/* ============ TAB 1: BENCHMARK ============ */}
          <TabsContent value="benchmark" className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <BarChart3 className="h-4 w-4 text-teal-700" /> Multi-site cross-validation
                  <span className="text-xs font-normal text-slate-500">
                    {sstr(multisite.scheme, 200)}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Stat label="Sites" value={intg(multisite.n_sites) || "6"} sub={`${countries.length || 7} countries`} />
                  <Stat
                    label="Ensemble ROC-AUC"
                    value={msSummary.length ? num(msSummary[msSummary.length - 1].roc_auc_mean, 4) : "—"}
                    sub={msSummary.length ? `± ${num(msSummary[msSummary.length - 1].roc_auc_std, 4)} across folds` : ""}
                  />
                  <Stat
                    label="Bootstrap 95% CI"
                    value={
                      (() => {
                        const g = gapRows.find((x) => Number(x.gap) === 1);
                        const ci = rec(g?.roc_auc_ci95);
                        return ci.lower !== undefined ? `[${num(ci.lower, 3)}, ${num(ci.upper, 3)}]` : "—";
                      })()
                    }
                    sub="1,000 iterations (Gap 1)"
                  />
                  <Stat
                    label="Multi-seed stability"
                    value={
                      (() => {
                        const g = gapRows.find((x) => Number(x.gap) === 5);
                        return g?.mean !== undefined ? `${num(g.mean, 3)} ± ${num(g.std, 3)}` : "—";
                      })()
                    }
                    sub="seeds 42/123/456/789/1024 (Gap 5)"
                  />
                </div>

                <div className="mt-4 h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={msFolds.map((f, i) => ({
                        name: `Fold ${intg(f.fold)} (${arr(f.held_out_sites).map((x) => sstr(x, 22)).join(", ").slice(0, 26)})`,
                        Ensemble: Number(f.ensemble?.roc_auc) || 0,
                        Classical: Number(f.classical?.roc_auc) || 0,
                        MLP: Number(f.mlp?.roc_auc) || 0,
                      }))}
                      margin={{ top: 8, right: 10, left: -22, bottom: 44 }}
                    >
                      <CartesianGrid strokeDasharray="2 4" stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#64748b" }} angle={-25} textAnchor="end" interval={0} />
                      <YAxis domain={[0.5, 1.0]} tick={{ fontSize: 10, fill: "#64748b" }} />
                      <RTooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                      <Legend wrapperStyle={{ fontSize: 10 }} />
                      <Bar dataKey="Ensemble" fill="#0f766e" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="Classical" fill="#14b8a6" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="MLP" fill="#f59e0b" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="mt-4 overflow-x-auto rounded-md border border-slate-200">
                  <Table>
                    <TableHeader className="bg-slate-100">
                      <TableRow>
                        <TableHead className="text-xs">Model</TableHead>
                        <TableHead className="text-xs">ROC-AUC (mean ± std)</TableHead>
                        <TableHead className="text-xs">Min</TableHead>
                        <TableHead className="text-xs">Max</TableHead>
                        <TableHead className="text-xs">Sensitivity</TableHead>
                        <TableHead className="text-xs">Specificity</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {msSummary.map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs font-semibold">{sstr(r.model, 40)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(r.roc_auc_mean, 4)} ± {num(r.roc_auc_std, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(r.roc_auc_min, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(r.roc_auc_max, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(r.sensitivity_mean, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(r.specificity_mean, 4)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* cross-lineage transfer */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Activity className="h-4 w-4 text-teal-700" /> Cross-lineage transfer
                  <span className="text-xs font-normal text-slate-500">{sstr(lineage.scheme, 220)}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto rounded-md border border-slate-200">
                  <Table>
                    <TableHeader className="bg-slate-100">
                      <TableRow>
                        <TableHead className="text-xs">Held-out lineage</TableHead>
                        <TableHead className="text-xs">n cells</TableHead>
                        <TableHead className="text-xs">n PSCs</TableHead>
                        <TableHead className="text-xs">Ensemble ROC-AUC</TableHead>
                        <TableHead className="text-xs">Classical</TableHead>
                        <TableHead className="text-xs">MLP</TableHead>
                        <TableHead className="text-xs">Sensitivity</TableHead>
                        <TableHead className="text-xs">Specificity</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {linRows.map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs font-semibold capitalize">{sstr(r.held_out_lineage, 20)}</TableCell>
                          <TableCell className="font-mono text-xs">{intg(r.n_test)}</TableCell>
                          <TableCell className="font-mono text-xs">{intg(r.n_test_psc)}</TableCell>
                          <TableCell className="font-mono text-xs font-bold text-teal-800">{num(rec(r.ensemble).roc_auc, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(rec(r.classical).roc_auc, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(rec(r.mlp).roc_auc, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(rec(r.ensemble).sensitivity, 4)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(rec(r.ensemble).specificity, 4)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* gap fixes */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <CheckCircle2 className="h-4 w-4 text-teal-700" /> Publication gap fixes
                  <span className="text-xs font-normal text-slate-500">
                    {gapSummary.all_closed === true ? "all 7 closed" : "see results/gap_fix_summary.json"}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 md:grid-cols-2">
                  {gapRows.map((g, i) => (
                    <div key={i} className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-slate-800">
                          Gap {intg(g.gap)} · {sstr(g.title, 80)}
                        </div>
                        <div className="truncate text-[11px] text-slate-500">
                          {Number(g.gap) === 1 ? `CI [${num(rec(g.roc_auc_ci95).lower, 3)}, ${num(rec(g.roc_auc_ci95).upper, 3)}] · ${intg(g.n_iterations)} iters` : ""}
                          {Number(g.gap) === 2 ? `resipsc ${num(g.resipsc_auc, 3)} vs Kuroda ${num(g.kuroda_auc, 3)} · DeLong p=${num(g.delong_p, 3)}` : ""}
                          {Number(g.gap) === 3 ? `full ensemble ${num(g.full_ensemble_auc, 3)} · ${arr(g.configurations).length} configs` : ""}
                          {Number(g.gap) === 4 ? `FP ${num(g.fp_before, 4)} → ${num(g.fp_after, 4)}` : ""}
                          {Number(g.gap) === 5 ? `${num(g.mean, 3)} ± ${num(g.std, 3)} (5 seeds)` : ""}
                          {Number(g.gap) === 6 ? "paper/wet_lab_limitation.md" : ""}
                          {Number(g.gap) === 7 ? "300 DPI, 6 panels (A-F)" : ""}
                        </div>
                      </div>
                      <Badge className={sstr(g.status, 10) === "closed" ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100" : "bg-amber-100 text-amber-800 hover:bg-amber-100"}>
                        {sstr(g.status, 10) || "—"}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* ICH Q5E comparability demo */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldCheck className="h-4 w-4 text-teal-700" /> ICH Q5E comparability (model promotion gate)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-slate-600">
                  Runs a live promotion-gate study: current production model vs a freshly trained candidate
                  (seed 123) on the frozen golden corpus. Acceptance: |Δsens| ≤ 0.02, |Δspec| ≤ 0.02, κ ≥ 0.90.
                </p>
                <Button onClick={() => void runComparability()} disabled={compBusy} className="bg-teal-700 text-white hover:bg-teal-800">
                  {compBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Activity className="mr-2 h-4 w-4" />}
                  {compBusy ? "Running comparability… (~1 min)" : "Run ICH Q5E comparability"}
                </Button>
                {comparability && (
                  <div className="grid gap-2 md:grid-cols-4">
                    <Stat label="Verdict" value={sstr(comparability.verdict, 40)} sub="acceptance criteria" />
                    <Stat label="Cohen's κ" value={num(comparability.cohens_kappa, 4)} sub="≥ 0.90 required" />
                    <Stat label="Δ sensitivity" value={num(comparability.sensitivity_delta, 4)} sub="|Δ| ≤ 0.02 required" />
                    <Stat label="Δ specificity" value={num(comparability.specificity_delta, 4)} sub="|Δ| ≤ 0.02 required" />
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* ============ TAB 2: SENSITIVITY ============ */}
          <TabsContent value="sensitivity" className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <FlaskConical className="h-4 w-4 text-teal-700" /> PSC spike-in sensitivity sweep
                  <span className="text-xs font-normal text-slate-500">{sstr(spikein.headline, 200)}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Stat
                    label="Detection limit"
                    value={spikein.limit_of_detection_fraction !== undefined && spikein.limit_of_detection_fraction !== null ? `${(100 * Number(spikein.limit_of_detection_fraction)).toFixed(3)}%` : "—"}
                    sub="recall ≥ 0.5"
                  />
                  <Stat
                    label="Calibration (sens)"
                    value={num(rec(spikein.quantification_calibration).sens, 4)}
                    sub="spike-in derived"
                  />
                  <Stat
                    label="Calibration (FPR)"
                    value={num(rec(spikein.quantification_calibration).fpr, 4)}
                    sub="spike-in derived"
                  />
                  <Stat label="Base cells" value={intg(spikein.n_base_cells) || "2000"} sub="per replicate" />
                </div>

                <div className="mt-4 h-72 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={spAgg.map((a) => ({
                        name: `${num(a.true_pct, 3)}%`,
                        recall: 100 * (Number(a.recall_mean) || 0),
                        estimated: Number(a.estimated_pct_mean) || 0,
                        true: Number(a.true_pct) || 0,
                      }))}
                      margin={{ top: 8, right: 10, left: -18, bottom: 18 }}
                    >
                      <CartesianGrid strokeDasharray="2 4" stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} />
                      <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                      <RTooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                      <Legend wrapperStyle={{ fontSize: 10 }} />
                      <Bar dataKey="true" name="True PSC %" fill="#0f766e" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="estimated" name="Calibrated estimate %" fill="#14b8a6" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="recall" name="Recall %" fill="#f59e0b" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="mt-4 overflow-x-auto rounded-md border border-slate-200">
                  <Table>
                    <TableHeader className="bg-slate-100">
                      <TableRow>
                        <TableHead className="text-xs">True fraction</TableHead>
                        <TableHead className="text-xs">Recall (mean ± std)</TableHead>
                        <TableHead className="text-xs">Precision</TableHead>
                        <TableHead className="text-xs">Raw measured</TableHead>
                        <TableHead className="text-xs">Calibrated estimate</TableHead>
                        <TableHead className="text-xs">Replicates</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {spAgg.map((a, i) => (
                        <TableRow key={i}>
                          <TableCell className="font-mono text-xs font-semibold">{num(a.true_pct, 4)}%</TableCell>
                          <TableCell className="font-mono text-xs">
                            {num(a.recall_mean, 3)} ± {num(a.recall_std, 3)}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{num(a.precision_mean, 3)}</TableCell>
                          <TableCell className="font-mono text-xs text-slate-500">{num(a.raw_pct_mean, 4)}%</TableCell>
                          <TableCell className="font-mono text-xs font-bold text-teal-800">{num(a.estimated_pct_mean, 4)}%</TableCell>
                          <TableCell className="font-mono text-xs">{intg(a.n_replicates)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* wet-lab reference lines */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Microscope className="h-4 w-4 text-teal-700" /> Wet-lab method comparison
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {arr(spikein.wet_lab_reference_lines).map((w, i) => {
                  const pctv = Number(w.pct) || 0;
                  const detected = spikein.limit_of_detection_fraction !== null
                    ? pctv >= Number(spikein.limit_of_detection_fraction)
                    : false;
                  return (
                    <div
                      key={i}
                      className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                        detected ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"
                      }`}
                    >
                      <div className="text-xs font-medium text-slate-800">{sstr(w.label, 120)}</div>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-xs text-slate-600">LOD {pctv.toFixed(4)}%</span>
                        <Badge
                          className={
                            detected
                              ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-100"
                          }
                        >
                          {detected ? "within resipsc range" : "below resipsc validated floor"}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
                <p className="pt-1 text-[11px] leading-relaxed text-slate-500">
                  resipsc quantification is calibrated on the spike-in validation sweep (affine correction of
                  the raw threshold count). Estimates are conservative (over-estimate) below 0.1% — the safe
                  direction for a contaminant screen. All LOD figures for wet-lab methods are published
                  literature values; no wet-lab validation has been performed for resipsc (see paper/wet_lab_limitation.md).
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          {/* === PART3 === */}
          {/* ============ TAB 3: QC REPORT ============ */}
          <TabsContent value="qc" className="space-y-4">
            {/* ---- upload system ---- */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Upload className="h-4 w-4 text-teal-700" /> Run a QC analysis
                  <span className="text-xs font-normal text-slate-500">
                    three upload paths: server file · direct (&lt;5 MB) · chunked (1 MB, sequential)
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-end gap-3">
                  <div className="w-48">
                    <label className="mb-1 block text-xs font-medium text-slate-600">Batch ID</label>
                    <Input
                      value={batchId}
                      onChange={(e) => setBatchId(e.target.value.slice(0, 40))}
                      placeholder="BATCH-001"
                      className="font-mono text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">
                      Upload a file (h5ad / csv / mtx)
                    </label>
                    <input
                      ref={fileRef}
                      type="file"
                      accept=".h5ad,.csv,.tsv,.mtx,.h5,.txt,.parquet"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void runQcOnFile(f);
                        e.target.value = "";
                      }}
                    />
                    <Button
                      onClick={() => fileRef.current?.click()}
                      disabled={qcBusy !== null}
                      className="bg-teal-700 text-white hover:bg-teal-800"
                    >
                      {qcBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <FileUp className="mr-2 h-4 w-4" />}
                      {qcBusy ? "Working…" : "Choose file"}
                    </Button>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                  <span className="font-medium">Quick select (server files):</span>
                  {[
                    { path: "data/pbmc3k_raw.h5ad", label: "pbmc3k — real, RELEASE demo" },
                    { path: "results/clean_batch.h5ad", label: "borderline — HOLD demo" },
                    { path: "results/golden_batch.h5ad", label: "contaminated — QUARANTINE demo" },
                  ].map((q) => (
                    <Button
                      key={q.path}
                      size="sm"
                      variant="outline"
                      disabled={qcBusy !== null}
                      onClick={() => void runQcOnPath(q.path)}
                      className="h-7 border-teal-300 px-2 text-[11px] text-teal-800 hover:bg-teal-50"
                    >
                      <Server className="mr-1 h-3 w-3" /> {q.label}
                    </Button>
                  ))}
                </div>

                {/* progress bar (chunked uploads) */}
                {upload && (
                  <div className="space-y-1.5 rounded-md border border-teal-200 bg-teal-50 p-3">
                    <div className="flex justify-between text-xs text-teal-900">
                      <span>
                        {upload.phase === "analysing"
                          ? "Assembled — running QC pipeline…"
                          : `Uploading chunk ${upload.chunk}/${upload.chunks}`}
                      </span>
                      <span className="font-mono">
                        {(upload.bytes / 1e6).toFixed(2)} / {(upload.total / 1e6).toFixed(2)} MB
                      </span>
                    </div>
                    <Progress value={Math.max(2, (100 * upload.bytes) / Math.max(1, upload.total))} className="h-2" />
                  </div>
                )}

                {qcBusy && !upload && (
                  <div className="flex items-center gap-2 rounded-md border border-teal-200 bg-teal-50 p-3 text-xs text-teal-900">
                    <Loader2 className="h-4 w-4 animate-spin" /> {qcBusy}
                  </div>
                )}

                {qcErr && (
                  <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800">
                    <strong>QC failed:</strong> {qcErr}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ---- previous batches ---- */}
            <PreviousBatches onOpen={runQcOnPath} />

            {/* ---- elevated report ---- */}
            {report ? (
              <ElevatedQcReport report={report} onDownloadPdf={() => void downloadPdf()} pdfBusy={pdfBusy} />
            ) : (
              !qcBusy &&
              !upload && (
                <Card>
                  <CardContent className="py-12 text-center">
                    <FileCheck2 className="mx-auto h-10 w-10 text-slate-300" />
                    <p className="mt-3 text-sm text-slate-500">
                      Select a server file or upload an h5ad/CSV to generate the elevated QC report
                      (15+ sections, 14-page PDF export, Part 11 audit logging).
                    </p>
                  </CardContent>
                </Card>
              )
            )}
          </TabsContent>

          {/* === PART4 === */}
          {/* ============ TAB 4: DATASETS ============ */}
          <TabsContent value="datasets" className="space-y-4">
            {/* where was the model trained? */}
            <div className="rounded-xl border-2 border-teal-700 bg-teal-800 p-5 text-white shadow">
              <div className="flex items-center gap-2">
                <Database className="h-5 w-5" />
                <h2 className="text-lg font-bold">Where was the model trained?</h2>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-lg bg-teal-900/50 p-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-teal-200">Corpus</div>
                  <div className="mt-1 text-sm">{trainingLabel || "—"}</div>
                  <div className="mt-1 text-[11px] text-teal-200">
                    {intg(training.n_cells) || "—"} cells · {intg(training.n_psc) || "—"} PSCs ·{" "}
                    {arr(training.datasets).length || registry.length} datasets
                  </div>
                </div>
                <div className="rounded-lg bg-teal-900/50 p-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-teal-200">Provenance</div>
                  <div className="mt-1 text-[11px] leading-relaxed text-teal-100">
                    {sstr(training.provenance, 420) ||
                      "Synthetic multi-site simulations + real PBMC negative reference with cross-batch noise."}
                  </div>
                </div>
              </div>
              <div className="mt-3 text-[11px] text-teal-200">
                Model card: {sstr(card.config_hash, 20) ? `config hash ${sstr(card.config_hash, 20)}` : "—"} ·
                data hash {sstr(rec(training).data_hash, 20) || "—"} · trained{" "}
                {sstr(card.generated_at_utc, 40) || "—"}
              </div>
            </div>

            {/* 10-step training protocol */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Microscope className="h-4 w-4 text-teal-700" /> Training protocol (10 steps)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="ml-4 list-decimal space-y-1 font-mono text-xs text-slate-700">
                  {[
                    "1. Simulate 6 multi-site publications (7 countries, 3 germ layers) with batch effects, doublets, ambient RNA, low-quality cells, dropout",
                    "2. Load real pbmc3k negative reference (800 cells, cross-batch noise applied)",
                    "3. QC filter (>=10 genes/cell, >=3 cells/gene, markers retained)",
                    "4. Library-size normalisation (10k counts) + log1p",
                    "5. HVG selection (top 300 by variance, marker panel forced)",
                    "6. Per-gene z-scaling with training statistics",
                    "7. Fit classical block (XGB 0.5 / RF 0.25 / SVM 0.25, calibrated)",
                    "8. Fit deep block (TruncatedSVD + AE embedding + calibrated MLP)",
                    "9. 4-fold OOF evaluation + quantification calibration (sens/fpr)",
                    "10. Persist model + card + registry; audit-log training & promotion",
                  ].map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </CardContent>
            </Card>

            {/* production note */}
            <Card className="border-amber-300 bg-amber-50">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base text-amber-900">
                  <AlertTriangle className="h-4 w-4" /> Production note (honest labelling)
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs leading-relaxed text-amber-900">
                This is a <strong>hybrid demonstration build</strong>: the synthetic corpus simulates
                manufacturing data realistically (including deliberately ambiguous partially-reprogrammed
                cells that cap achievable ROC-AUC below 1.0), and the real PBMC reference anchors the
                negative class in genuine biology. It is <strong>not</strong> trained on clinical
                manufacturing batches, and no wet-lab orthogonal validation has been performed.
                The Wellington 41,670-cell iPSC integration dataset (Census ID{" "}
                <span className="font-mono">5b0e8244-cc05-47ab-819f-87747854c04c</span>, ~599 MB) is
                the designated real-data upgrade path: place it at{" "}
                <span className="font-mono">data/real/iPSC_integration_41k.h5ad</span> and run{" "}
                <span className="font-mono">scripts/train_and_save.py</span> to retrain on real data
                (&ge; 8 GB RAM).
              </CardContent>
            </Card>

            {/* dataset registry */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Database className="h-4 w-4 text-teal-700" /> Training corpus registry
                  <span className="text-xs font-normal text-slate-500">{registry.length} datasets</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto rounded-md border border-slate-200">
                  <Table>
                    <TableHeader className="bg-slate-100">
                      <TableRow>
                        <TableHead className="text-xs">Dataset</TableHead>
                        <TableHead className="text-xs">Country</TableHead>
                        <TableHead className="text-xs">Protocol</TableHead>
                        <TableHead className="text-xs">Lineage</TableHead>
                        <TableHead className="text-xs">n cells</TableHead>
                        <TableHead className="text-xs">n PSC</TableHead>
                        <TableHead className="text-xs">PSC %</TableHead>
                        <TableHead className="text-xs">Source</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {registry.map((d, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-xs font-medium">{sstr(d.dataset_id, 40)}</TableCell>
                          <TableCell className="text-xs">{sstr(d.country, 24)}</TableCell>
                          <TableCell className="text-xs">{sstr(d.protocol, 30)}</TableCell>
                          <TableCell className="text-xs capitalize">{sstr(d.lineage, 24)}</TableCell>
                          <TableCell className="font-mono text-xs">{intg(d.n_cells)}</TableCell>
                          <TableCell className="font-mono text-xs">{intg(d.n_psc)}</TableCell>
                          <TableCell className="font-mono text-xs">{num(d.psc_pct, 2)}%</TableCell>
                          <TableCell className="text-[11px] text-slate-600">{sstr(d.source, 40)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ============ TAB 5: CALIBRATION ============ */}
          <TabsContent value="calibration" className="space-y-4">
            <CalibrationTab />
          </TabsContent>
        </Tabs>
      </div>

      {/* ================= footer ================= */}
      <footer className="mt-10 border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-[11px] text-slate-500 md:px-8">
          <span>
            resipsc v2.0.0 · residual PSC detection for cell therapy QC · Research Use Only — NOT
            FDA-cleared
          </span>
          <span className="font-mono">
            21 CFR Part 11 audit: db/audit.db (SHA-256 chained) · ICH Q9 FMEA · Q5E comparability ·
            PCCP change control
          </span>
        </div>
      </footer>
    </main>
  );
}

/* ================================================================== */
/* Stat tile                                                            */
/* ================================================================== */

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 truncate font-mono text-lg font-bold text-slate-900" title={value}>
        {value}
      </div>
      {sub ? <div className="truncate text-[10px] text-slate-500" title={sub}>{sub}</div> : null}
    </div>
  );
}

/* ================================================================== */
/* Previous batches list (QC tab)                                       */
/* ================================================================== */

function PreviousBatches({ onOpen }: { onOpen: (path: string) => void }) {
  const [batches, setBatches] = useState<AnyRec[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/resipsc/batches", { cache: "no-store" });
        const json = (await res.json()) as AnyRec;
        if (!cancelled) setBatches(arr(json.batches));
      } catch {
        if (!cancelled) setBatches([]);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loaded) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Calendar className="h-4 w-4 text-teal-700" /> Previous QC reports
          <span className="text-xs font-normal text-slate-500">{batches.length} batches</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {batches.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500">
            No QC runs recorded yet on this server.
          </div>
        ) : (
          <div className="max-h-72 overflow-y-auto rounded-md border border-slate-200">
            <Table>
              <TableHeader className="sticky top-0 bg-slate-100">
                <TableRow>
                  <TableHead className="text-[11px]">Batch</TableHead>
                  <TableHead className="text-[11px]">Generated (UTC)</TableHead>
                  <TableHead className="text-[11px]">Decision</TableHead>
                  <TableHead className="text-[11px]">Tier</TableHead>
                  <TableHead className="text-[11px]">Cells</TableHead>
                  <TableHead className="text-[11px]">PSC fraction</TableHead>
                  <TableHead className="text-[11px]">Agreement</TableHead>
                  <TableHead className="text-[11px] w-20"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {batches.map((b, i) => {
                  const dec = sstr(b.decision, 16);
                  return (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-[11px]">{sstr(b.batch_id, 28)}</TableCell>
                      <TableCell className="text-[11px] text-slate-600">{sstr(b.generated_at_utc, 24)}</TableCell>
                      <TableCell>
                        <Badge
                          className={
                            dec === "RELEASE"
                              ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"
                              : dec === "HOLD"
                                ? "bg-amber-100 text-amber-800 hover:bg-amber-100"
                                : "bg-rose-100 text-rose-800 hover:bg-rose-100"
                          }
                        >
                          {dec}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-[11px]">{sstr(b.risk_tier, 4) || "—"}</TableCell>
                      <TableCell className="font-mono text-[11px]">{intg(b.input_total_cells) || intg(b.n_cells)}</TableCell>
                      <TableCell className="font-mono text-[11px]">
                        {b.estimated_psc_fraction !== null && b.estimated_psc_fraction !== undefined
                          ? `${(100 * Number(b.estimated_psc_fraction)).toFixed(4)}%`
                          : "—"}
                      </TableCell>
                      <TableCell className="font-mono text-[11px]">
                        {b.biomarker_model_agreement !== null && b.biomarker_model_agreement !== undefined
                          ? `${(100 * Number(b.biomarker_model_agreement)).toFixed(1)}%`
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 border-teal-300 px-2 text-[10px] text-teal-800 hover:bg-teal-50"
                          onClick={() => onOpen(sstr(b.input_file, 200))}
                          title={sstr(b.input_file, 200)}
                        >
                          Re-run
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ================================================================== */
/* Calibration tab (drift monitoring)                                   */
/* ================================================================== */

function CalibrationTab() {
  const [cal, setCal] = useState<AnyRec | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filePath, setFilePath] = useState("data/pbmc3k_raw.h5ad");
  const [batchId, setBatchId] = useState("DRIFT-CHECK");

  const load = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/calibration", { cache: "no-store" });
      const json = (await res.json()) as AnyRec;
      setCal(json);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const runCheck = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/calibration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filePath, batchId }),
      });
      const json = (await res.json()) as AnyRec;
      if (json.status !== "ok") throw new Error(sstr(json.message, 300) || "check failed");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [filePath, batchId, load]);

  const latest = rec(cal?.latest);
  const metrics = rec(cal?.latest_metrics);
  const thresholds = rec(cal?.thresholds);
  const history = arr(cal?.history);

  const timelineData = history.map((h, i) => ({
    name: `#${i + 1} ${sstr(h.batch_id, 18)}`,
    KL: Number(h.kl_divergence) || 0,
    JS: Number(h.js_divergence) || 0,
    Wasserstein: Number(h.wasserstein) || 0,
  }));

  const drifted = sstr(metrics.status, 10) === "DRIFTED";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge className="h-4 w-4 text-teal-700" /> Calibration drift monitoring
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* status banner */}
        <div
          className={`rounded-lg border p-3 ${
            drifted ? "border-rose-300 bg-rose-50" : "border-emerald-300 bg-emerald-50"
          }`}
        >
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {drifted ? (
              <ShieldAlert className="h-5 w-5 text-rose-600" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-emerald-600" />
            )}
            <span className="font-bold text-slate-800">
              {cal?.baseline_established === true ? "Model ready — baseline established" : "Baseline pending"}
            </span>
            <span className="text-xs text-slate-600">
              baseline {intg(cal?.baseline_n_cells)} scores · {intg(cal?.batches_monitored)} batches
              monitored
            </span>
          </div>
        </div>

        {/* drift metric tiles */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { k: "KL divergence", v: metrics.kl, thr: thresholds.kl },
            { k: "JS divergence", v: metrics.js, thr: thresholds.js },
            { k: "Wasserstein", v: metrics.wasserstein, thr: thresholds.wasserstein },
            { k: "KS statistic", v: metrics.ks, thr: thresholds.ks },
          ].map((m) => {
            const val = Number(m.v);
            const thr = Number(m.thr);
            const bad = Number.isFinite(val) && Number.isFinite(thr) && val > thr;
            return (
              <div
                key={m.k}
                className={`rounded-lg border p-3 ${bad ? "border-rose-300 bg-rose-50" : "border-emerald-200 bg-emerald-50"}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-600">{m.k}</span>
                  <Badge
                    className={
                      bad
                        ? "bg-rose-100 text-rose-800 hover:bg-rose-100"
                        : "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"
                    }
                  >
                    {bad ? "DRIFTED" : "STABLE"}
                  </Badge>
                </div>
                <div className="mt-1 font-mono text-lg font-bold text-slate-900">{num(m.v, 4)}</div>
                <div className="text-[10px] text-slate-500">threshold {num(m.thr, 3)}</div>
              </div>
            );
          })}
        </div>

        {/* run a drift check */}
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="w-64">
            <label className="mb-1 block text-[11px] font-medium text-slate-600">File to check (server path)</label>
            <Input value={filePath} onChange={(e) => setFilePath(e.target.value)} className="h-8 font-mono text-xs" />
          </div>
          <div className="w-40">
            <label className="mb-1 block text-[11px] font-medium text-slate-600">Batch label</label>
            <Input value={batchId} onChange={(e) => setBatchId(e.target.value)} className="h-8 font-mono text-xs" />
          </div>
          <Button onClick={() => void runCheck()} disabled={busy} className="h-8 bg-teal-700 text-white hover:bg-teal-800">
            {busy ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Beaker className="mr-1.5 h-3.5 w-3.5" />}
            Run drift check
          </Button>
        </div>

        {err && (
          <div className="rounded-md border border-rose-300 bg-rose-50 p-2 text-xs text-rose-800">{err}</div>
        )}

        {/* drift timeline */}
        {timelineData.length > 0 && (
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timelineData} margin={{ top: 8, right: 10, left: -22, bottom: 4 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 8, fill: "#64748b" }} />
                <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                <RTooltip contentStyle={{ fontSize: 11, borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <ReferenceLine y={Number(thresholds.kl) || 0.1} stroke="#e11d48" strokeDasharray="4 2" label={{ value: "KL threshold", fill: "#e11d48", fontSize: 9 }} />
                <Line type="monotone" dataKey="KL" stroke="#0f766e" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="JS" stroke="#14b8a6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Wasserstein" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* calibration history */}
        {history.length > 0 && (
          <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200">
            <Table>
              <TableHeader className="sticky top-0 bg-slate-100">
                <TableRow>
                  <TableHead className="text-[11px]">Timestamp (UTC)</TableHead>
                  <TableHead className="text-[11px]">Batch</TableHead>
                  <TableHead className="text-[11px]">n cells</TableHead>
                  <TableHead className="text-[11px]">mean P</TableHead>
                  <TableHead className="text-[11px]">KL</TableHead>
                  <TableHead className="text-[11px]">JS</TableHead>
                  <TableHead className="text-[11px]">Wass.</TableHead>
                  <TableHead className="text-[11px]">KS</TableHead>
                  <TableHead className="text-[11px]">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...history].reverse().map((h, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-[11px] text-slate-600">{sstr(h.timestamp_utc, 24)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{sstr(h.batch_id, 24)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{intg(h.n_cells)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(h.mean_probability, 4)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(h.kl_divergence, 4)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(h.js_divergence, 4)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(h.wasserstein, 4)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(h.ks_statistic, 4)}</TableCell>
                    <TableCell>
                      <Badge
                        className={
                          sstr(h.status, 10) === "DRIFTED"
                            ? "bg-rose-100 text-rose-800 hover:bg-rose-100"
                            : "bg-emerald-100 text-emerald-800 hover:bg-emerald-100"
                        }
                      >
                        {sstr(h.status, 10)}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
