"use client";

import { useMemo, useState, useCallback } from "react";
import { useAnalysis } from "../hooks/useAnalysis";
import { useLivePrice } from "../hooks/useLivePrice";
import { useRule1History } from "../hooks/useRule1History";
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

function fmtDateTime(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
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
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-500">No diagnostics.</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((d, i) => {
        const tone =
          d.severity === "critical" || d.severity === "high"
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
              <span className="text-xs uppercase tracking-wide">{d.severity}</span>
            </div>
            <p className="text-sm mt-1">{d.message}</p>

            {d.evidence ? (
              <pre className="mt-2 rounded bg-white/60 p-2 text-xs overflow-x-auto">
                {JSON.stringify(d.evidence, null, 2)}
              </pre>
            ) : null}

            {d.recommendation ? (
              <p className="text-xs mt-1">
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
    error,
    valuation,
    applicability,
    dataQuality,
    freshness,
    recompute,
  } = useAnalysis(symbol, { analytics });

  const { loading: loadingHistory, error: historyError, history, reload: reloadHistory } =
    useRule1History(symbol);

  const [recomputing, setRecomputing] = useState(false);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await recompute();
      // After recompute, refresh history so the new run appears
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [recompute, reloadHistory]);

  const { price, currency: priceCcy, loading: loadingPrice } = useLivePrice(symbol);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const uncomputableReason = useMemo(() => {
    return applicability?.flags?.find((f) => f.code === "UNCOMPUTABLE_RULE1")?.message;
  }, [applicability?.flags]);

  const summary = useMemo(() => {
    const curr = valuation?.currency ?? "USD";

    return (
      <Card>
        <CardHeader>
          <CardTitle>Intrinsic Value Summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!loading && uncomputableReason ? (
            <div className="rounded border bg-slate-50 p-3 text-sm">
              {uncomputableReason}
            </div>
          ) : null}

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
              <Skeleton className="h-20" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Metric label="Sticker Price" value={fmtCurrency(valuation?.stickerPrice, curr)} />
              <Metric label="MOS Price" value={fmtCurrency(valuation?.mosPrice, curr)} />
              <Metric
                label="Current Price"
                value={
                  loadingPrice ? (
                    <span className="text-slate-400">Loading…</span>
                  ) : price != null ? (
                    fmtCurrency(price, priceCcy ?? curr)
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
                <> • Last evaluated: {freshness.lastEvaluatedDisplay}</>
              ) : null}
            </div>

            <Button onClick={handleRecompute} disabled={recomputing}>
              {recomputing ? "Recomputing…" : "Recompute"}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }, [
    loading,
    valuation,
    freshness,
    recomputing,
    loadingPrice,
    price,
    priceCcy,
    uncomputableReason,
    handleRecompute,
  ]);

  const breakdown = useMemo(() => {
    const v: Rule1Valuation | undefined = valuation;
    const curr = v?.currency ?? "USD";
    const decisions = dataQuality?.inputDecisions;

    const eps0 =
      v?.eps0 ??
      (typeof decisions?.eps0?.value === "number" ? decisions.eps0.value : undefined);

    const growth =
      v?.growth ??
      (typeof decisions?.growth?.valueClamped === "number"
        ? decisions.growth.valueClamped
        : undefined);

    const futurePE =
      v?.futurePE ??
      (typeof decisions?.futurePE?.selected === "number"
        ? decisions.futurePE.selected
        : undefined);

    const discountRate =
      v?.discountRate ??
      (typeof decisions?.assumptions?.discountRate === "number"
        ? decisions.assumptions.discountRate
        : undefined);

    const horizonYears =
      v?.horizonYears ??
      (typeof decisions?.assumptions?.horizonYears === "number"
        ? decisions.assumptions.horizonYears
        : undefined);

    const mosPct =
      v?.mos ??
      (typeof decisions?.assumptions?.mos === "number"
        ? decisions.assumptions.mos
        : undefined);

    // ✅ Fix: cached path often sets futureEPS=0.0; derive if needed
    const futureEPSDerived =
      typeof eps0 === "number" &&
      typeof growth === "number" &&
      typeof horizonYears === "number"
        ? eps0 * Math.pow(1 + growth, horizonYears)
        : undefined;

    const futureEPS =
      typeof v?.futureEPS === "number" && v.futureEPS > 0 ? v.futureEPS : futureEPSDerived;

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
              <Metric label="EPS₀" value={fmtCurrency(eps0, curr)} />
              <Metric label="Growth" value={fmtPct(growth)} />
              <Metric label="Future EPS" value={fmtCurrency(futureEPS, curr)} />
              <Metric label="Future P/E" value={fmtInt(futurePE)} />
              <Metric label="Discount Rate" value={fmtPct(discountRate)} />
              <Metric label="Horizon" value={`${horizonYears ?? "—"} yrs`} />
              <Metric label="MOS %" value={fmtPct(mosPct)} />
            </div>
          )}
        </CardContent>
      </Card>
    );
  }, [loading, valuation, dataQuality?.inputDecisions]);

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
            <ScoreBar score={applicability?.score} category={applicability?.category} />
          )}

          {!loading && uncomputableReason ? (
            <div className="rounded border bg-slate-50 p-3 text-sm">{uncomputableReason}</div>
          ) : null}

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

          <button className="text-sm underline" onClick={() => setShowDiagnostics((v) => !v)}>
            {showDiagnostics ? "Hide diagnostics" : "Show diagnostics"}
          </button>

          {showDiagnostics && <DiagnosticsList items={applicability?.flags} />}
        </CardContent>
      </Card>
    );
  }, [loading, applicability, showDiagnostics, uncomputableReason]);

  const historyCard = useMemo(() => {
    const items = history?.items ?? [];
    const curr = valuation?.currency ?? "USD";

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
          ) : historyError ? (
            <div className="text-sm text-slate-600">
              Could not load history.{" "}
              <button className="underline" onClick={() => void reloadHistory()}>
                Retry
              </button>
            </div>
          ) : items.length === 0 ? (
            <p className="text-sm text-slate-500">No history yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[220px]">Date</TableHead>
                  <TableHead>Sticker</TableHead>
                  <TableHead>MOS</TableHead>
                  <TableHead>Growth</TableHead>
                  <TableHead>Future P/E</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Category</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((r, idx) => (
                  <TableRow key={`${r.runAt}-${idx}`}>
                    <TableCell>{fmtDateTime(r.runAt)}</TableCell>
                    <TableCell>{fmtCurrency(r.stickerPrice, curr)}</TableCell>
                    <TableCell>{fmtCurrency(r.mosPrice, curr)}</TableCell>
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
  }, [loadingHistory, historyError, history, reloadHistory, valuation?.currency]);

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded border border-rose-200 bg-rose-50 p-3 text-rose-700">
          {error}
        </div>
      ) : null}

      {summary}
      {breakdown}
      {suitability}

      <Separator />

      {historyCard}
    </div>
  );
}