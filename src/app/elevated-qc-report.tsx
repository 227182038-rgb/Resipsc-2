"use client";

/**
 * elevated-qc-report.tsx — the 15+ section elevated QC report (v2.0/v2.1).
 *
 * Renders every field emitted by ResipscEnsemble.qc_report_dict():
 * cover banner, hero decision, key metrics, probability distribution,
 * statistical confidence, calibration gauges, regulatory context,
 * recommendations, methodology, threshold sensitivity, per-cell
 * classification, QC flags, clinical notification, disease-site
 * probabilities, cell projection (PCA), gene heatmap, batch history,
 * model credentials, disclaimer, citation + metadata, and PDF/print
 * actions.
 *
 * All numeric rendering is defensive (PART 3.10): every value coerces
 * safely and never throws on undefined.
 */

import { useMemo } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  Beaker,
  Brain,
  Calendar,
  CheckCircle2,
  ClipboardList,
  Database,
  FileDown,
  Flag,
  FlaskConical,
  Gauge,
  Info,
  Microscope,
  Printer,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface QcReport {
  [key: string]: unknown;
}

type AnyRec = Record<string, unknown>;

/* ------------------------------------------------------------------ */
/* defensive formatting helpers (PART 3.10)                             */
/* ------------------------------------------------------------------ */

export function num(v: unknown, nd = 4): string {
  if (typeof v === "number" && Number.isFinite(v)) return v.toFixed(nd);
  if (typeof v === "string" && v !== "" && Number.isFinite(Number(v))) return Number(v).toFixed(nd);
  return "n/a";
}

export function pct(v: unknown, nd = 4): string {
  if (typeof v === "number" && Number.isFinite(v)) return `${(100 * v).toFixed(nd)}%`;
  return "n/a";
}

export function intg(v: unknown): string {
  if (typeof v === "number" && Number.isFinite(v)) return String(Math.round(v));
  if (typeof v === "string" && v !== "") return v;
  return "0";
}

function str(v: unknown, max = 1000): string {
  if (typeof v === "string") return v.slice(0, max);
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return "";
}

function rec(v: unknown): AnyRec {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as AnyRec) : {};
}

function arr(v: unknown): AnyRec[] {
  return Array.isArray(v) ? (v as AnyRec[]) : [];
}

/* decision colour palette (teal family + amber/rose; no blue/indigo) */
const DECISION_STYLE: Record<string, { bg: string; border: string; text: string; icon: typeof ShieldCheck }> = {
  RELEASE: { bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-700", icon: BadgeCheck },
  HOLD: { bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-700", icon: AlertTriangle },
  QUARANTINE: { bg: "bg-rose-50", border: "border-rose-300", text: "text-rose-700", icon: ShieldAlert },
};

const TIER_STYLE: Record<string, string> = {
  T1: "bg-emerald-100 text-emerald-800 border-emerald-300",
  T2: "bg-teal-100 text-teal-800 border-teal-300",
  T3: "bg-amber-100 text-amber-800 border-amber-300",
  T4: "bg-rose-100 text-rose-800 border-rose-300",
};

const CLASS_COLORS: Record<string, string> = {
  high_confidence_psc: "#e11d48",
  model_only_psc: "#f59e0b",
  biomarker_only_psc: "#0d9488",
  ambiguous: "#94a3b8",
  high_confidence_negative: "#0f766e",
};

/* ================================================================== */
/* main component                                                       */
/* ================================================================== */

export function ElevatedQcReport({
  report,
  onDownloadPdf,
  pdfBusy,
}: {
  report: QcReport;
  onDownloadPdf?: () => void;
  pdfBusy?: boolean;
}) {
  const r = report;

  /* pre-extract all sections (defensively) */
  const rm = rec(r.report_metadata);
  const es = rec(r.executive_summary);
  const rt = rec(r.risk_tier);
  const sc = rec(r.statistical_confidence);
  const boot = rec(sc.bootstrap_ci_95);
  const binom = rec(sc.binomial_test);
  const power = rec(sc.post_hoc_power);
  const dist = rec(r.probability_distribution);
  const calib = rec(r.calibration_metrics);
  const regx = rec(r.regulatory_context);
  const meth = rec(r.methodology);
  const tsens = rec(r.threshold_sensitivity);
  const pcc = rec(r.per_cell_classification);
  const dsp = rec(r.disease_site_probabilities);
  const cn = rec(r.clinical_notification);
  const proj = rec(r.cell_projection);
  const heat = rec(r.gene_heatmap);
  const bhist = rec(r.batch_history);
  const creds = rec(r.model_credentials);
  const disc = rec(r.disclaimer);
  const cite = rec(r.citation_block);

  const decision = str(r.decision, 20) || "UNKNOWN";
  const dstyle = DECISION_STYLE[decision] ?? DECISION_STYLE.HOLD;
  const DecisionIcon = dstyle.icon;

  const binsData = useMemo(
    () =>
      arr(dist.bins).map((b, i) => ({
        name: str(b.label, 16) || `bin${i}`,
        count: typeof b.count === "number" ? b.count : 0,
        fraction: typeof b.fraction === "number" ? b.fraction : 0,
      })),
    [dist.bins],
  );

  const scatterData = useMemo(() => {
    const groups: Record<string, Array<{ x: number; y: number; p: number; id: string }>> = {};
    for (const pt of arr(proj.points)) {
      const cls = str(pt.class, 40) || "high_confidence_negative";
      const x = typeof pt.x === "number" ? pt.x : 0;
      const y = typeof pt.y === "number" ? pt.y : 0;
      (groups[cls] ??= []).push({ x, y, p: typeof pt.p === "number" ? pt.p : 0, id: str(pt.cell_id, 40) });
    }
    return groups;
  }, [proj.points]);

  const histBatches = useMemo(
    () =>
      arr(bhist.batches).slice(-10).map((b) => ({
        batch: str(b.batch_id, 24) || "?",
        decision: str(b.decision, 16) || "?",
        date: str(b.generated_at_utc, 24) || "?",
        n: typeof b.n_cells === "number" ? b.n_cells : 0,
        frac: typeof b.estimated_psc_fraction === "number" ? 100 * b.estimated_psc_fraction : 0,
        agreement: typeof b.biomarker_model_agreement === "number" ? 100 * b.biomarker_model_agreement : null,
      })),
    [bhist.batches],
  );

  const heatGenes = arr2str(heat.genes);
  const heatTop = arr(heat.top_cells);
  const heatBottom = arr(heat.bottom_cells);
  const heatMax = useMemo(() => {
    let m = 0;
    for (const c of [...heatTop, ...heatBottom]) {
      for (const v of arr2num(c.values)) m = Math.max(m, v);
    }
    return m || 1;
  }, [heatTop, heatBottom]);

  const savedPath = str(r.saved_report_path, 300);

  return (
    <div className="space-y-5">
      {/* ============ 1. cover banner ============ */}
      <div className="rounded-xl border border-teal-800 bg-gradient-to-r from-teal-900 via-teal-800 to-teal-700 p-5 text-white shadow-lg print:border-none print:shadow-none">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-[0.25em] text-teal-200">resipsc v2.0 · elevated QC report</div>
            <div className="mt-1 font-mono text-sm text-teal-100">
              report_id {str(rm.report_id, 24) || "—"} · seed {str(rm.input_hash_short, 16) || "—"}
            </div>
          </div>
          <div className="text-right text-xs text-teal-100">
            <div>{str(rm.generated_at_utc, 40) || "—"}</div>
            <div className="font-mono">{str(rm.batch_id, 40) || "—"}</div>
          </div>
        </div>
      </div>

      {/* ============ 2. hero decision card ============ */}
      <div className={`rounded-xl border-2 ${dstyle.border} ${dstyle.bg} p-6 print:border-slate-300 print:bg-white`}>
        <div className="flex flex-wrap items-start gap-5">
          <div className={`flex h-20 w-20 shrink-0 items-center justify-center rounded-full ${dstyle.bg} ${dstyle.border} border-2`}>
            <DecisionIcon className={`h-10 w-10 ${dstyle.text}`} aria-label={decision} />
          </div>
          <div className="min-w-[240px] flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <span className={`text-3xl font-black tracking-tight ${dstyle.text}`}>{decision}</span>
              <span className={`rounded-md border px-2.5 py-1 text-sm font-bold ${TIER_STYLE[str(rt.tier, 4)] || TIER_STYLE.T3}`}>
                {str(rt.tier, 4) || "T?"} · {str(rt.numerical_threshold, 20) || "—"}
              </span>
              <span className="text-sm text-slate-600">{str(rt.label, 80)}</span>
            </div>
            <p className="text-base font-semibold text-slate-800">{str(es.headline, 300)}</p>
            <p className="text-sm leading-relaxed text-slate-700">{str(es.detail, 600)}</p>
            <p className="text-xs italic text-slate-600">⚠ {str(es.caveat, 500)}</p>
            <p className="text-sm font-medium text-slate-800">One-line verdict: {str(es.one_line_verdict, 200)}</p>
          </div>
        </div>
        <Separator className="my-4" />
        <p className="text-sm text-slate-700">{str(r.decision_reason, 600)}</p>
      </div>

      {/* ============ 3. key metrics row ============ */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          { label: "Cells analysed", value: intg(r.n_cells), sub: r.input_total_cells ? `${intg(r.input_total_cells)} in file${r.subsampled ? " (subsampled)" : ""}` : "" },
          { label: "Detected PSCs", value: intg(r.estimated_psc_count), sub: `${intg(r.n_cells_above_threshold)} above threshold` },
          { label: "Est. fraction", value: pct(r.estimated_psc_fraction, 4), sub: `raw ${pct(r.raw_measured_fraction, 4)}` },
          { label: "Biomarker agreement", value: pct(r.biomarker_model_agreement, 1), sub: str(r.cross_check_warning, 60) },
          { label: "Max P(PSC)", value: num(r.psc_probability_max), sub: `mean ${num(r.psc_probability_mean)}` },
        ].map((m) => (
          <Card key={m.label} className="border-slate-200 print:border-slate-300">
            <CardContent className="p-3">
              <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{m.label}</div>
              <div className="mt-1 text-xl font-bold text-slate-900">{m.value}</div>
              <div className="mt-0.5 truncate text-[11px] text-slate-500" title={m.sub}>{m.sub}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* ============ 4. probability distribution ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Gauge className="h-4 w-4 text-teal-700" /> 4 · PSC probability distribution (20 bins)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={binsData} margin={{ top: 5, right: 10, left: -18, bottom: 18 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#e2e8f0" />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 8, fill: "#64748b" }}
                  interval={2}
                  angle={-55}
                  textAnchor="end"
                />
                <YAxis tick={{ fontSize: 10, fill: "#64748b" }} />
                <RTooltip
                  contentStyle={{ fontSize: 11, borderRadius: 8, borderColor: "#cbd5e1" }}
                  formatter={(v: number | string) => [`${v} cells`, "count"]}
                />
                <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                  {binsData.map((_, i) => (
                    <Cell key={i} fill={i < 5 ? "#0f766e" : i < 9 ? "#14b8a6" : i < 13 ? "#f59e0b" : "#e11d48"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-600 md:grid-cols-5">
            {[
              ["p50", num(dist.p50)],
              ["p95", num(dist.p95)],
              ["p99", num(dist.p99)],
              ["mean", num(dist.mean)],
              ["max", num(dist.max)],
            ].map(([k, v]) => (
              <div key={k} className="rounded bg-slate-50 px-2 py-1 text-center">
                <span className="font-semibold text-slate-800">{k}</span> <span className="font-mono">{v}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ============ 5. statistical confidence ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-teal-700" /> 5 · Statistical confidence
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Bootstrap 95% CI (fraction)</div>
            <div className="mt-2 font-mono text-lg font-bold text-teal-800">
              [{num(boot.lower, 5)}, {num(boot.upper, 5)}]
            </div>
            <div className="mt-1 text-xs text-slate-600">
              mean {num(boot.mean, 5)} ± {num(boot.std, 5)} · {intg(boot.n_iterations)} iterations
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Binomial test vs release limit</div>
            <div className="mt-2 font-mono text-lg font-bold text-teal-800">p = {num(binom.p_value, 6)}</div>
            <div className="mt-1 text-xs text-slate-600">
              observed {intg(binom.observed_count)} vs expected {num(binom.expected_under_null, 3)} under null
            </div>
            <div className="mt-1 text-xs font-semibold">
              {binom.significant_at_alpha_0_05 ? (
                <span className="text-rose-600">significant at α=0.05</span>
              ) : (
                <span className="text-emerald-700">not significant at α=0.05</span>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Post-hoc power</div>
            <div className="mt-2 font-mono text-lg font-bold text-teal-800">{num(power.value, 3)}</div>
            <div className="mt-1 text-xs text-slate-600">{str(power.interpretation, 160)}</div>
          </div>
        </CardContent>
      </Card>

      {/* ============ 6. calibration gauges ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Gauge className="h-4 w-4 text-teal-700" /> 6 · Calibration vs biomarker reference
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          {[
            { label: "Brier score", value: num(calib.brier_score_vs_biomarker, 4), frac: 1 - Math.min(1, Number(calib.brier_score_vs_biomarker) || 0), note: str(calib.brier_interpretation, 160), good: (Number(calib.brier_score_vs_biomarker) ?? 0) < 0.15 },
            { label: "ECE (surrogate)", value: num(calib.ece_surrogate_vs_biomarker, 4), frac: 1 - Math.min(1, Number(calib.ece_surrogate_vs_biomarker) || 0), note: str(calib.ece_interpretation, 160), good: (Number(calib.ece_surrogate_vs_biomarker) ?? 0) < 0.15 },
            { label: "Biomarker agreement", value: pct(calib.biomarker_model_agreement, 1), frac: Number(calib.biomarker_model_agreement) || 0, note: "concordance of model calls with the OCT4/NANOG/SOX2 panel", good: (Number(calib.biomarker_model_agreement) ?? 0) >= 0.8 },
          ].map((g) => (
            <div key={g.label} className="rounded-lg border border-slate-200 p-3">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{g.label}</span>
                <span className={`font-mono text-lg font-bold ${g.good ? "text-emerald-700" : "text-amber-600"}`}>{g.value}</span>
              </div>
              <Progress value={Math.max(2, Math.min(100, 100 * (Number.isFinite(g.frac) ? g.frac : 0)))} className="mt-2 h-2" />
              <p className="mt-2 text-[11px] leading-snug text-slate-600">{g.note}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ============ 7. regulatory context ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardList className="h-4 w-4 text-teal-700" /> 7 · Regulatory context
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {[
            { k: "FDA 21 CFR 1271 / 211 / Part 11", v: regx.fda },
            { k: "EMA EMEA/CHMP/410869/2006", v: regx.ema },
            { k: "ICH Q5E / Q9(R1) / Q10", v: regx.ich },
          ].map((x) => (
            <div key={x.k} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-xs font-bold text-teal-800">{x.k}</div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-slate-700">{str(x.v, 800)}</p>
            </div>
          ))}
          <div className="md:col-span-3 flex flex-wrap gap-2 text-xs text-slate-600">
            <Badge variant="outline" className="border-teal-300 text-teal-800">
              Disposition code: {str(regx.disposition_code, 20)}
            </Badge>
            <Badge variant="outline" className="border-teal-300 text-teal-800">
              Observed fraction: {num(regx.observed_psc_fraction_pct, 4)}%
            </Badge>
            <Badge variant="outline" className="border-teal-300 text-teal-800">
              Audit trail: {str(regx.audit_trail, 80)}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* ============ 8. recommendations ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4 text-teal-700" /> 8 · Recommendations (priority ranked)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">#</TableHead>
                <TableHead className="w-20">Priority</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Rationale</TableHead>
                <TableHead className="w-28">Owner</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {arr(r.recommendations).map((recm, i) => (
                <TableRow key={i}>
                  <TableCell className="font-mono text-xs">{intg(recm.priority)}</TableCell>
                  <TableCell>
                    <Badge
                      className={
                        Number(recm.priority) <= 1
                          ? "bg-rose-100 text-rose-800 hover:bg-rose-100"
                          : Number(recm.priority) === 2
                            ? "bg-amber-100 text-amber-800 hover:bg-amber-100"
                            : "bg-slate-100 text-slate-700 hover:bg-slate-100"
                      }
                    >
                      P{intg(recm.priority)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">{str(recm.category, 40)}</TableCell>
                  <TableCell className="text-xs">{str(recm.action, 160)}</TableCell>
                  <TableCell className="text-[11px] text-slate-600">{str(recm.rationale, 200)}</TableCell>
                  <TableCell className="text-xs">{str(recm.owner, 40)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ============ 9. methodology ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Microscope className="h-4 w-4 text-teal-700" /> 9 · Methodology
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(rec(meth.model_versions)).map(([k, v]) => (
              <Badge key={k} variant="outline" className="border-slate-300 font-mono text-[10px] text-slate-700">
                {k} {str(v, 12)}
              </Badge>
            ))}
          </div>
          <ol className="ml-4 list-decimal space-y-1 text-xs text-slate-700">
            {arr2str(meth.pipeline).map((step, i) => (
              <li key={i} className="font-mono">{str(step, 120)}</li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2 text-xs text-slate-600">
            <Badge variant="outline" className="border-teal-300 text-teal-800">
              decision threshold {num(rec(meth.input_dimensions).cells !== undefined ? meth.decision_threshold : undefined)}
            </Badge>
            <Badge variant="outline" className="border-teal-300 text-teal-800">
              seed {intg(meth.random_seed)}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* ============ 10. threshold sensitivity ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Gauge className="h-4 w-4 text-teal-700" /> 10 · Threshold sensitivity
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(rec(tsens.thresholds)).map(([k, v]) => {
              const t = rec(v);
              return (
                <div key={k} className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-center">
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">threshold {k}</div>
                  <div className="mt-1 font-mono text-lg font-bold text-slate-900">{intg(t.n_above)}</div>
                  <div className="text-xs text-slate-600">cells ({num(t.fraction_pct, 4)}%)</div>
                </div>
              );
            })}
          </div>
          <div
            className={`mt-3 rounded-md px-3 py-2 text-xs font-medium ${
              tsens.all_thresholds_agree ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"
            }`}
          >
            {tsens.all_thresholds_agree ? "✓ " : "⚠ "}
            {str(tsens.decision_stability, 300)}
          </div>
        </CardContent>
      </Card>

      {/* ============ 11. per-cell classification ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Brain className="h-4 w-4 text-teal-700" /> 11 · Per-cell classification (model × biomarker)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {[
              { k: "high_confidence_psc", label: "High-confidence PSC", c: "border-rose-300 bg-rose-50 text-rose-800" },
              { k: "model_only_psc", label: "Model-only PSC", c: "border-amber-300 bg-amber-50 text-amber-800" },
              { k: "biomarker_only_psc", label: "Biomarker-only", c: "border-teal-300 bg-teal-50 text-teal-800" },
              { k: "ambiguous", label: "Ambiguous", c: "border-slate-300 bg-slate-50 text-slate-700" },
              { k: "high_confidence_negative", label: "High-confidence negative", c: "border-emerald-300 bg-emerald-50 text-emerald-800" },
            ].map((cls) => {
              const cnt = rec(pcc.counts)[cls.k];
              const fracv = rec(pcc.fractions)[cls.k];
              return (
                <div key={cls.k} className={`rounded-lg border p-3 text-center ${cls.c}`}>
                  <div className="text-[10px] font-semibold uppercase leading-tight tracking-wide">{cls.label}</div>
                  <div className="mt-1 font-mono text-xl font-bold">{intg(cnt)}</div>
                  <div className="text-[11px] opacity-80">{pct(fracv, 2)}</div>
                </div>
              );
            })}
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {Object.entries(rec(pcc.interpretation)).map(([k, v]) => (
              <div key={k} className="rounded-md border border-slate-200 p-2">
                <div className="text-[11px] font-bold text-slate-700">{k}</div>
                <div className="text-[11px] leading-snug text-slate-600">{str(v, 300)}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ============ 12. QC flags ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Flag className="h-4 w-4 text-teal-700" /> 12 · QC flags
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {arr(r.qc_flags).length === 0 && <div className="text-xs text-slate-500">no flags</div>}
          {arr(r.qc_flags).map((f, i) => {
            const sev = str(f.severity, 12);
            const style =
              sev === "critical"
                ? "border-rose-300 bg-rose-50"
                : sev === "warning"
                  ? "border-amber-300 bg-amber-50"
                  : "border-slate-200 bg-slate-50";
            const icon =
              sev === "critical" ? (
                <XCircle className="h-4 w-4 shrink-0 text-rose-600" />
              ) : sev === "warning" ? (
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
              ) : (
                <Info className="h-4 w-4 shrink-0 text-slate-500" />
              );
            return (
              <div key={i} className={`flex items-start gap-2 rounded-md border p-2.5 ${style}`}>
                {icon}
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slate-800">
                    <span className="uppercase">{sev}</span> · {str(f.category, 40)}
                  </div>
                  <div className="text-xs text-slate-700">{str(f.message, 300)}</div>
                  <div className="text-[11px] text-slate-600">→ {str(f.action, 200)}</div>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* ============ 13. clinical notification ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Beaker className="h-4 w-4 text-teal-700" /> 13 · Clinical notification — teratoma risk
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-teal-200 bg-teal-50 p-3">
            <div className="text-sm font-bold text-teal-900">{str(cn.title, 160)}</div>
            <p className="mt-1 text-xs leading-relaxed text-teal-900">{str(cn.risk_summary, 500)}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-teal-900">
              <Badge variant="outline" className="border-teal-400">
                confidence: {str(cn.confidence, 20)}
              </Badge>
              <Badge variant="outline" className="border-teal-400">
                PSC count: {intg(cn.overall_psc_count)} / {intg(cn.total_cells_analysed)} cells
              </Badge>
            </div>
          </div>
          <div className="max-h-96 overflow-y-auto rounded-md border border-slate-200">
            <Table>
              <TableHeader className="sticky top-0 bg-slate-100">
                <TableRow>
                  <TableHead className="text-[11px]">Anatomical site</TableHead>
                  <TableHead className="text-[11px]">Layer</TableHead>
                  <TableHead className="text-[11px]">Abs. risk</TableHead>
                  <TableHead className="text-[11px]">Level</TableHead>
                  <TableHead className="text-[11px]">Confirmatory assay</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {arr(cn.teratoma_risk_sites)
                  .slice(0, 22)
                  .map((s, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-xs font-medium">{str(s.anatomical_site, 60)}</TableCell>
                      <TableCell className="text-[11px] text-slate-600">{str(s.germ_layer, 20)}</TableCell>
                      <TableCell className="font-mono text-[11px]">{num(s.absolute_risk_probability, 4)}</TableCell>
                      <TableCell>
                        <Badge
                          className={
                            str(s.risk_level, 12) === "HIGH"
                              ? "bg-rose-100 text-rose-800 hover:bg-rose-100"
                              : str(s.risk_level, 12) === "MODERATE"
                                ? "bg-amber-100 text-amber-800 hover:bg-amber-100"
                                : "bg-slate-100 text-slate-600 hover:bg-slate-100"
                          }
                        >
                          {str(s.risk_level, 14)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-[11px] text-slate-600">{str(s.confirmatory_assay, 120)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] italic text-slate-500">{str(cn.disclaimer, 400)}</p>
        </CardContent>
      </Card>

      {/* ============ 14. disease site probabilities ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldAlert className="h-4 w-4 text-teal-700" /> 14 · Disease site probabilities
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[
              { k: "high_risk_sites", label: "High risk", c: "border-rose-300 bg-rose-50 text-rose-800" },
              { k: "moderate_risk_sites", label: "Moderate risk", c: "border-amber-300 bg-amber-50 text-amber-800" },
              { k: "low_risk_sites", label: "Low risk", c: "border-teal-300 bg-teal-50 text-teal-800" },
              { k: "negligible_risk_sites", label: "Negligible", c: "border-slate-300 bg-slate-50 text-slate-700" },
            ].map((x) => (
              <div key={x.k} className={`rounded-lg border p-3 text-center ${x.c}`}>
                <div className="text-[10px] font-semibold uppercase tracking-wide">{x.label}</div>
                <div className="font-mono text-xl font-bold">{intg(dsp[x.k])}</div>
              </div>
            ))}
          </div>
          <div className="max-h-80 overflow-y-auto rounded-md border border-slate-200">
            <Table>
              <TableHeader className="sticky top-0 bg-slate-100">
                <TableRow>
                  <TableHead className="text-[11px]">Site</TableHead>
                  <TableHead className="text-[11px]">Layer</TableHead>
                  <TableHead className="text-[11px]">Cells in lineage</TableHead>
                  <TableHead className="text-[11px]">Lineage prob.</TableHead>
                  <TableHead className="text-[11px]">Site prior</TableHead>
                  <TableHead className="text-[11px]">Abs. risk</TableHead>
                  <TableHead className="text-[11px]">Level</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {arr(dsp.sites).map((s, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs">{str(s.anatomical_site, 50)}</TableCell>
                    <TableCell className="text-[11px] text-slate-600">{str(s.germ_layer, 16)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{intg(s.predicted_cells_in_lineage)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(s.lineage_probability, 4)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(s.site_prior, 3)}</TableCell>
                    <TableCell className="font-mono text-[11px]">{num(s.absolute_risk_probability, 4)}</TableCell>
                    <TableCell className="text-[10px] font-semibold">{str(s.risk_level, 14)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-[11px] text-slate-500">
            {str(dsp.formula, 200)} · priors: {str(dsp.priors_source, 300)} · {intg(dsp.total_sites_evaluated)} sites evaluated
          </p>
        </CardContent>
      </Card>

      {/* ============ 15. cell projection ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-teal-700" /> 15 · Cell projection ({str(proj.method, 10)} · {intg(proj.n_cells_projected)} of {intg(proj.n_cells_total)} cells)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 16, left: -18, bottom: 4 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#e2e8f0" />
                <XAxis
                  type="number"
                  dataKey="x"
                  tick={{ fontSize: 10, fill: "#64748b" }}
                  domain={arr2num(proj.x_range).length === 2 ? [arr2num(proj.x_range)[0], arr2num(proj.x_range)[1]] : ["auto", "auto"]}
                />
                <YAxis type="number" dataKey="y" tick={{ fontSize: 10, fill: "#64748b" }} />
                <RTooltip
                  contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  formatter={(v: number | string, n: string) => [typeof v === "number" ? v.toFixed(3) : v, n === "x" ? "PC1" : n === "y" ? "PC2" : n]}
                  labelFormatter={() => ""}
                />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                {Object.entries(scatterData).map(([cls, pts]) => (
                  <Scatter key={cls} name={cls} data={pts} fill={CLASS_COLORS[cls] ?? "#94a3b8"} fillOpacity={0.72} />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            Colour = model × biomarker classification (red: high-confidence PSC · amber: model-only · teal: biomarker-only ·
            grey: ambiguous · dark-teal: negative). Projection is {str(proj.method, 10) === "umap" ? "UMAP" : str(proj.method, 10) === "pca" ? "PCA (first two components)" : "random"}.
          </p>
        </CardContent>
      </Card>

      {/* ============ 16. gene heatmap ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <FlaskConical className="h-4 w-4 text-teal-700" /> 16 · Pluripotency marker heatmap ({heatGenes.length} genes × {heatTop.length + heatBottom.length} cells)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <HeatRows label="Top-scoring cells" cells={heatTop} genes={heatGenes} max={heatMax} />
          <HeatRows label="Bottom-scoring cells" cells={heatBottom} genes={heatGenes} max={heatMax} />
          <p className="text-[11px] text-slate-500">{str(heat.description, 300)} · scale: {str(heat.color_scale, 120)}</p>
        </CardContent>
      </Card>

      {/* ============ 17. batch history ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Calendar className="h-4 w-4 text-teal-700" /> 17 · Batch history ({intg(bhist.n_previous_batches)} previous · trend: {str(bhist.trend, 24)})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {histBatches.length === 0 ? (
            <div className="rounded-md border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500">
              This is the first analysed batch on this server — history will accumulate as QC runs are executed.
            </div>
          ) : (
            <div className="max-h-72 overflow-y-auto rounded-md border border-slate-200">
              <Table>
                <TableHeader className="sticky top-0 bg-slate-100">
                  <TableRow>
                    <TableHead className="text-[11px]">Batch</TableHead>
                    <TableHead className="text-[11px]">Date (UTC)</TableHead>
                    <TableHead className="text-[11px]">Decision</TableHead>
                    <TableHead className="text-[11px]">Cells</TableHead>
                    <TableHead className="text-[11px]">PSC fraction</TableHead>
                    <TableHead className="text-[11px]">Agreement</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {histBatches.map((b, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-mono text-[11px]">{b.batch}</TableCell>
                      <TableCell className="text-[11px] text-slate-600">{b.date}</TableCell>
                      <TableCell className="text-[11px] font-semibold">{b.decision}</TableCell>
                      <TableCell className="font-mono text-[11px]">{b.n}</TableCell>
                      <TableCell className="font-mono text-[11px]">{b.frac.toFixed(4)}%</TableCell>
                      <TableCell className="font-mono text-[11px]">{b.agreement === null ? "—" : `${b.agreement.toFixed(1)}%`}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ============ 18. model credentials ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Database className="h-4 w-4 text-teal-700" /> 18 · Model credentials
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {[
            { k: "Model version", v: str(creds.model_version, 60) },
            { k: "Benchmark", v: str(creds.benchmark, 200) },
            { k: "Sensitivity", v: str(creds.sensitivity, 200) },
            { k: "Training data", v: str(creds.training_data, 240) },
            { k: "Software", v: `resipsc ${str(rm.software_version, 12)} · report v${str(rm.report_version, 8)}` },
            { k: "Intended use", v: str(rm.intended_use, 160) },
          ].map((x) => (
            <div key={x.k} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{x.k}</div>
              <div className="mt-1 text-xs text-slate-800">{x.v || "—"}</div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* ============ 19. disclaimer ============ */}
      <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-5 print:break-inside-avoid">
        <div className="flex items-center gap-2 text-sm font-bold text-amber-800">
          <AlertTriangle className="h-4 w-4" /> 19 · Disclaimer
        </div>
        <p className="mt-2 text-sm font-semibold text-amber-900">{str(disc.primary, 400)}</p>
        <div className="mt-3 space-y-1.5">
          {arr2str(disc.limitations).map((lim, i) => (
            <div key={i} className="flex gap-2 text-xs text-amber-900">
              <span>•</span>
              <span>{str(lim, 300)}</span>
            </div>
          ))}
        </div>
        <Separator className="my-3 bg-amber-200" />
        <p className="text-xs text-amber-900">
          <strong>Wet-lab confirmation:</strong> {str(disc.wet_lab_confirmation, 400)}
        </p>
        <p className="mt-1.5 text-xs text-amber-900">
          <strong>Decision authority:</strong> {str(disc.decision_authority, 400)}
        </p>
        <p className="mt-1.5 text-xs text-amber-900">
          <strong>Audit trail:</strong> {str(disc.audit_trail, 300)}
        </p>
      </div>

      {/* ============ 20. citation + metadata footer ============ */}
      <Card className="print:break-inside-avoid">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Info className="h-4 w-4 text-teal-700" /> 20 · Citation & report metadata
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-md bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-teal-100">
            {str(cite.bibtex, 800)}
          </div>
          <p className="text-xs text-slate-700">{str(cite.citation_text, 500)}</p>
          <div className="grid gap-2 text-[11px] text-slate-600 md:grid-cols-2">
            <div>DOI: {str(cite.doi_placeholder, 80)}</div>
            <div>License: {str(cite.license, 80)}</div>
            <div>Software Heritage: {str(cite.software_heritage_id, 80)}</div>
            <div>Input: {str(r.input_file, 120)}</div>
            <div>Format: {str(rm.input_file_format, 20)} · {intg(rm.input_cells)} cells × {intg(rm.input_genes)} genes</div>
            <div>Signature: {str(rm.signature_line, 120)}</div>
          </div>
        </CardContent>
      </Card>

      {/* ============ 21. actions ============ */}
      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <Button
          onClick={onDownloadPdf}
          disabled={pdfBusy || !savedPath}
          className="bg-teal-700 text-white hover:bg-teal-800"
        >
          <FileDown className="mr-2 h-4 w-4" />
          {pdfBusy ? "Rendering PDF…" : "Download QC Report PDF (14 pages)"}
        </Button>
        <Button variant="outline" onClick={() => window.print()} className="border-teal-300 text-teal-800 hover:bg-teal-50">
          <Printer className="mr-2 h-4 w-4" /> Print / Save PDF
        </Button>
        {savedPath ? (
          <span className="text-xs text-slate-500">saved: {savedPath}</span>
        ) : null}
      </div>
    </div>
  );
}

/* ================================================================== */
/* helpers                                                              */
/* ================================================================== */

function arr2str(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function arr2num(v: unknown): number[] {
  return Array.isArray(v) ? v.filter((x): x is number => typeof x === "number" && Number.isFinite(x)) : [];
}

function HeatRows({
  label,
  cells,
  genes,
  max,
}: {
  label: string;
  cells: AnyRec[];
  genes: string[];
  max: number;
}) {
  if (cells.length === 0 || genes.length === 0) {
    return <div className="text-xs text-slate-400">{label}: no data</div>;
  }
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="overflow-x-auto">
        <div className="min-w-max">
          <div className="flex">
            <div className="w-32 shrink-0" />
            {genes.map((g) => (
              <div key={g} className="w-16 shrink-0 truncate px-1 text-center text-[9px] font-semibold text-slate-600" title={g}>
                {g}
              </div>
            ))}
          </div>
          {cells.map((c, i) => (
            <div key={i} className="flex items-center">
              <div className="w-32 shrink-0 truncate pr-2 text-[9px] font-mono text-slate-500" title={str(c.cell_id, 60)}>
                {str(c.cell_id, 24)} ({num(c.p, 2)})
              </div>
              {arr2num(c.values).slice(0, genes.length).map((v, j) => (
                <div
                  key={j}
                  className="m-[1px] h-5 w-16 shrink-0 rounded-sm"
                  style={heatStyle(v, max)}
                  title={`${genes[j] ?? "?"}: ${v.toFixed(2)}`}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** blue -> white -> red gradient on log-normalised expression. */
function heatStyle(v: number, max: number): React.CSSProperties {
  const t = Math.max(0, Math.min(1, v / (max || 1)));
  if (t <= 0.5) {
    const u = t / 0.5;
    const r = Math.round(224 + (255 - 224) * u);
    const g = Math.round(242 + (255 - 242) * u);
    const b = Math.round(254 + (255 - 254) * u);
    const bg = `rgb(${r - 160 * u}, ${g - 100 * u}, ${b - 40 * u})`;
    return { backgroundColor: bg };
  }
  const u = (t - 0.5) / 0.5;
  const r = 255;
  const g = Math.round(255 - 165 * u);
  const b = Math.round(255 - 235 * u);
  return { backgroundColor: `rgb(${r}, ${g}, ${b})` };
}
