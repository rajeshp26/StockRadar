// src/features/analysis/components/intrinsic-panel.tsx
"use client";

import { useState, useMemo } from "react";
import { useAnalysis } from "../hooks/useAnalysis";
import { usePrice } from "../hooks/usePrice";
import type { DiagnosticFlag, Rule1Valuation } from "../types/analysis.types";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import type { AnalysisAnalytics } from "@/features/analysis/analytics/analysis.analytics";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

/* ---------------------------------------------------------- */
/* Formatting helpers                                          */
/* ---------------------------------------------------------- */

function fmtCurrency(n?: number, currency = "USD") {
  if (n == null || Number.isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    }).format(n);
  } catch {
    return `$${n.toFixed(2)}`;
  }
}

function fmtPct(n?: number, digits = 1) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

function fmtInt(n?: number) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n)}`;
}

/* ---------------------------------------------------------- */
/* Visual subcomponents                                        */
/* ---------------------------------------------------------- */

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number | JSX.Element;
  hint?: string;
}) {
  return (
    <div className="rounded border p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-medium">{value}</div>
      {hint ? <div className="text-xs text-slate-400 mt-1">{hint}</div> : null}
    </div>
  );
}

function ScoreBar({
  score,
  category,
}: {
  score?: number;
  category?: string;
}) {
  const normalized = Math.max(0, Math.min(100, score ?? 0));
  const color =
    category === "Good"
      ? "bg-emerald-600"
      : category === "Caution"
      ? "bg-amber-600"
      : category === "Poor"
      ? "bg-rose-600"
      : "bg-slate-600";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-44 rounded bg-slate-200">
        <div
          className={`h-2 rounded ${color}`}
          style={{ width: `${normalized}%` }}
        />
      </div>
      <span className="text-sm text-slate-600">{fmtInt(score)} / 100</span>
      {category ? <Badge variant="secondary">{category}</Badge> : null}
    </div>
  );
}

function DiagnosticsList({ items }: { items?: DiagnosticFlag[] }) {
  if (!items || items.length === 0)
    return <p className="text-sm text-slate-500">No diagnostics.</p>;

  return (
    <div className="space-y-2">
      {items.map((d, i) => {
        const tone =
          d.severity === "critical"
            ? "border-rose-200 bg-rose-50 text-rose-700"
            : d.severity === "high"
            ? "border-rose-200 bg-rose-50 text-rose-700"
            : d.severity === "medium"
            ? "border-amber-200 bg-amber-50 text-amber-700"
            : d.severity === "low"
            ? "border-sky-200 bg-sky-50 text-sky-700"
            : "border-slate-200 bg-slate-50 text-slate-700";
        return (
          <div key={`${d.code}-${i}`} className={`rounded border p-3 ${tone}`}>
            <div className="flex items-center gap-2">
              <Badge variant="outline">{d.code}</Badge>
              <span className="text-xs uppercase tracking-wide">
                {d.severity}
              </span>
            </div>
            <p className="text-sm mt-1">{d.message}</p>
            {d.evidence ? (
              <pre className="mt-2 rounded bg-white/60 p-2 text-xs text-slate-700 overflow-x-auto">
                {JSON.stringify(d.evidence, null, 2)}
              </pre>
            ) : null}
            {d.recommendation ? (
              <p className="text-xs text-slate-600 mt-1">
                <span className="font-medium">Recommendation: </span>
                {d.recommendation}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------- */
/* Main Panel                                                  */
/* ---------------------------------------------------------- */

export function IntrinsicPanel({
  symbol,
  analytics,
}: {
  symbol: string;
  analytics?: AnalysisAnalytics;
}) {
  const {
    loading,
    loadingHistory,
    error,
    valuation,
    applicability,
    dataQuality,
    freshness,
    history,
    recompute,
  } = useAnalysis(symbol, { analytics });

  // Current price (non-blocking, guarded)
  const { price, currency: priceCcy, loading: loadingPrice } = usePrice(symbol);

  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const summary = useMemo(() => {
    const curr = valuation?.currency ?? "USD";
    return (
      <Card>
        <CardHeader>
          <CardTitle>Intrinsic Value Summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Metric
                label="Sticker Price"
                value={fmtCurrency(valuation?.stickerPrice, curr)}
              />
              <Metric
                label="MOS Price"
                value={fmtCurrency(valuation?.mosPrice, curr)}
              />
              <Metric
                label="Current Price"
                value={
                  loadingPrice ? (
                    <span className="text-slate-400">Loading…</span>
                  ) : price != null ? (
                    <span>
                      {fmtCurrency(
                        price,
                        priceCcy ?? valuation?.currency ?? "USD"
                      )}
                    </span>
                  ) : (
                    <span className="text-slate-400">Not available</span>
                  )
                }
              />
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-600">
              Calculated using Rule #1 (Phil Town)
              {freshness?.lastEvaluatedDisplay ? (
                <>
                  {" • "}Last evaluated: {freshness.lastEvaluatedDisplay}
                </>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={() => recompute()} disabled={loading}>
                {loading ? "Recomputing…" : "Recompute"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }, [loading, valuation, freshness, recompute, loadingPrice, price, priceCcy]);

  const breakdown = useMemo(() => {
    const v: Rule1Valuation | undefined = valuation;
    const curr = v?.currency ?? "USD";

    return (
      <Card>
        <CardHeader>
          <CardTitle>How We Arrived Here</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="grid md:grid-cols-3 gap-4">
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : (
            <div className="grid md:grid-cols-3 gap-4">
              <Metric
                label="EPS₀"
                value={fmtCurrency(v?.eps0, curr)}
                hint="Trailing or TTM EPS"
              />
              <Metric label="Growth" value={fmtPct(v?.growth)} />
              <Metric
                label="Future EPS (10Y)"
                value={fmtCurrency(v?.futureEPS, curr)}
              />
              <Metric label="Future P/E" value={fmtInt(v?.futurePE)} />
              <Metric label="Discount Rate" value={fmtPct(v?.discountRate)} />
              <Metric
                label="Horizon"
                value={`${v?.horizonYears ?? "—"} yrs`}
              />
              <Metric label="MOS %" value={fmtPct(v?.mos)} />
            </div>
          )}
        </CardContent>
      </Card>
    );
  }, [loading, valuation]);

  const suitability = useMemo(() => {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Suitability</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            <Skeleton className="h-6 w-64" />
          ) : (
            <ScoreBar
              score={applicability?.score}
              category={applicability?.category}
            />
          )}

          {/* Show quick flags preview (top 3 by severity), full list under diagnostics */}
          {!loading && applicability?.flags?.length ? (
            <div className="flex flex-wrap gap-2">
              {applicability.flags.slice(0, 3).map((f, i) => (
                <Badge key={`${f.code}-${i}`} variant="outline">
                  {f.code}
                </Badge>
              ))}
              {applicability.flags.length > 3 ? (
                <span className="text-xs text-slate-500">
                  +{applicability.flags.length - 3} more
                </span>
              ) : null}
            </div>
          ) : null}

          <button
            className="text-sm text-slate-600 underline underline-offset-2"
            onClick={() => setShowDiagnostics((v) => !v)}
          >
            {showDiagnostics ? "Hide diagnostics" : "Show diagnostics"}
          </button>

          {showDiagnostics && <DiagnosticsList items={applicability?.flags} />}
        </CardContent>
      </Card>
    );
  }, [loading, applicability, showDiagnostics]);

  const historyTable = useMemo(() => {
    return (
      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingHistory ? (
            <div className="space-y-2">
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
              <Skeleton className="h-6" />
            </div>
          ) : !history?.items?.length ? (
            <p className="text-sm text-slate-500">No history yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[160px]">Date</TableHead>
                  <TableHead>Sticker</TableHead>
                  <TableHead>MOS</TableHead>
                  <TableHead>Growth</TableHead>
                  <TableHead>Future P/E</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Category</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.items.map((r, idx) => (
                  <TableRow key={idx}>
                    <TableCell>
                      {new Date(r.runAt).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      {fmtCurrency(r.sticker, valuation?.currency)}
                    </TableCell>
                    <TableCell>
                      {fmtCurrency(r.mos, valuation?.currency)}
                    </TableCell>
                    <TableCell>{fmtPct(r.growth)}</TableCell>
                    <TableCell>{fmtInt(r.futurePE)}</TableCell>
                    <TableCell>{fmtInt(r.score)}</TableCell>
                    <TableCell>{r.category ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    );
  }, [loadingHistory, history, valuation?.currency]);

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded border border-rose-200 bg-rose-50 text-rose-700 p-3">
          {error}
        </div>
      ) : null}

      {summary}
      {breakdown}
      {suitability}
      <Separator />
      {historyTable}

      {/* Optional: raw debug (safe to remove) */}
      {/* <pre className="text-xs text-slate-500 overflow-x-auto">
        {JSON.stringify({ valuation, dataQuality, applicability }, null, 2)}
      </pre> */}
    </div>
  );
}