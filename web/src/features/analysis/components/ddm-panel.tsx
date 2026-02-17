"use client";

import { useMemo, useState, useCallback } from "react";
import type { DdmVariant, DdmValuation } from "../types/analysis.types";

import { useDdmAnalysis } from "../hooks/useDdmAnalysis";
import { useDdmHistory } from "../hooks/useDdmHistory";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  Metric,
  ScoreBar,
  DiagnosticsList,
  FlagPill,
  fmtCurrency,
  fmtPct,
  fmtInt,
  fmtDateTime,
} from "./shared-ui";

export function DdmPanel({ symbol }: { symbol: string }) {
  const [variant, setVariant] = useState<DdmVariant>("gordon");

  const { loading, error, valuation, applicability, dataQuality, freshness, recompute } =
    useDdmAnalysis(symbol, variant);

  const { loading: loadingHistory, error: historyError, history, reload: reloadHistory } =
    useDdmHistory(symbol, variant);

  const [recomputing, setRecomputing] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await recompute();
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [recompute, reloadHistory]);

  const summary = useMemo(() => {
    const curr = valuation?.currency ?? "USD";
    return (
      <Card className="glass rounded-3xl border border-white/5 text-white relative overflow-hidden">
        <CardHeader className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <CardTitle>Dividend Discount Model (DDM)</CardTitle>

            <Tabs value={variant} onValueChange={(v) => setVariant(v as DdmVariant)}>
              <TabsList>
                <TabsTrigger value="gordon">Gordon</TabsTrigger>
                <TabsTrigger value="two_stage">Two‑Stage</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
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
              <Metric label="Intrinsic Value" value={fmtCurrency(valuation?.intrinsicValue, curr)} />
              <Metric label="Current Price" value={fmtCurrency(valuation?.currentPrice ?? null, curr)} />
              <Metric label="Upside / Downside" value={fmtPct(valuation?.upsideDownsidePct ?? null)} />
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="text-sm text-slate-400">
              Method: {valuation?.method ?? (variant === "gordon" ? "gordon" : "two_stage")}
              {freshness?.lastEvaluatedDisplay ? <> • Last evaluated: {freshness.lastEvaluatedDisplay}</> : null}
            </div>

            <Button onClick={handleRecompute} disabled={recomputing}>
              {recomputing ? "Recomputing…" : "Recompute"}
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }, [loading, valuation, freshness, recomputing, handleRecompute, variant]);

  const howArrived = useMemo(() => {
    const v: DdmValuation | undefined = valuation;
    const curr = v?.currency ?? "USD";
    const decisions = (dataQuality?.inputDecisions as any)?.ddm;

    const d0Src = decisions?.d0Source as string | undefined;
    const kSrc = decisions?.requiredReturn?.source as string | undefined;
    const gSrc = decisions?.dividendGrowthRate?.source as string | undefined;

    const isTwoStage = (v?.method ?? "gordon") === "two_stage";

    return (
      <Card className="glass rounded-3xl border border-white/5 text-white">
        <CardHeader>
          <CardTitle>How We Arrived Here</CardTitle>
        </CardHeader>

        <CardContent>
          {loading ? (
            <div className="grid md:grid-cols-3 gap-4">
              {Array.from({ length: 9 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : (
            <>
              <div className="grid md:grid-cols-3 gap-4">
                <Metric
                  label="D0 (Annual DPS)"
                  value={fmtCurrency(v?.currentDps, curr)}
                  hint={d0Src ? `Source: ${d0Src}` : undefined}
                />
                <Metric label="D1 (Next Year DPS)" value={fmtCurrency(v?.nextYearDps, curr)} />
                <Metric
                  label="g (Dividend Growth)"
                  value={fmtPct(v?.dividendGrowthRate)}
                  hint={gSrc ? `Source: ${gSrc}` : undefined}
                />

                <Metric
                  label="k (Required Return)"
                  value={fmtPct(v?.requiredReturn)}
                  hint={kSrc ? `Source: ${kSrc}` : undefined}
                />
                <Metric
                  label="Stability Check"
                  value={v ? (v.dividendGrowthRate < v.requiredReturn ? "g < k ✅" : "g ≥ k ⚠️") : "—"}
                />
                <Metric label="Model" value={isTwoStage ? "Two‑Stage" : "Gordon"} />
              </div>

              {isTwoStage ? (
                <div className="mt-4 grid md:grid-cols-3 gap-4">
                  <Metric label="High Growth Years (n)" value={v?.highGrowthYears ?? "—"} />
                  <Metric label="High Growth Rate (g1)" value={fmtPct(v?.highGrowthRate ?? null)} />
                  <Metric label="Stable Growth (g2)" value={fmtPct(v?.stableGrowthRate ?? null)} />

                  <Metric label="PV Stage 1" value={fmtCurrency(v?.pvStage1 ?? null, curr)} />
                  <Metric label="PV Terminal" value={fmtCurrency(v?.pvTerminal ?? null, curr)} />
                  <Metric label="Intrinsic = PV1 + PVt" value={fmtCurrency(v?.intrinsicValue ?? null, curr)} />
                </div>
              ) : (
                <div className="mt-4 text-sm text-slate-400">
                  Gordon model: <span className="font-mono">Intrinsic = D1 / (k − g)</span>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    );
  }, [loading, valuation, dataQuality, variant]);

  const suitability = useMemo(() => {
    return (
      <Card className="glass rounded-3xl border border-white/5 text-white">
        <CardHeader>
          <CardTitle>Suitability</CardTitle>
        </CardHeader>

        <CardContent className="space-y-3">
          {loading ? (
            <Skeleton className="h-6 w-64" />
          ) : (
            <ScoreBar score={applicability?.score} category={applicability?.category} />
          )}

          {!loading && applicability?.flags?.length ? (
            <div className="flex flex-wrap gap-2 items-center">
              {applicability.flags.slice(0, 3).map((f, i) => (
                <FlagPill key={`${f.code}-${i}`} text={f.code} />
              ))}
              {applicability.flags.length > 3 ? (
                <span className="text-xs text-slate-300">
                  +{applicability.flags.length - 3} more
                </span>
              ) : null}
            </div>
          ) : null}

          <button
            className="text-sm underline text-slate-300 hover:text-white"
            onClick={() => setShowDiagnostics((v) => !v)}
          >
            {showDiagnostics ? "Hide diagnostics" : "Show diagnostics"}
          </button>

          {showDiagnostics && <DiagnosticsList items={applicability?.flags} />}
        </CardContent>
      </Card>
    );
  }, [loading, applicability, showDiagnostics]);

  const historyCard = useMemo(() => {
    const items = history?.items ?? [];
    const curr = valuation?.currency ?? "USD";

    return (
      <Card className="glass rounded-3xl border border-white/5 text-white">
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
            <div className="text-sm text-slate-300">
              Could not load history.{" "}
              <button className="underline" onClick={() => void reloadHistory()}>
                Retry
              </button>
            </div>
          ) : items.length === 0 ? (
            <p className="text-sm text-slate-300">No history yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[220px]">Date</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead>Intrinsic</TableHead>
                  <TableHead>g</TableHead>
                  <TableHead>k</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Category</TableHead>
                </TableRow>
              </TableHeader>

              <TableBody>
                {items.map((r, idx) => (
                  <TableRow key={`${r.runAt}-${idx}`}>
                    <TableCell>{fmtDateTime(r.runAt)}</TableCell>
                    <TableCell>{r.method ?? (variant === "gordon" ? "gordon" : "two_stage")}</TableCell>
                    <TableCell>{fmtCurrency(r.intrinsicValue ?? null, curr)}</TableCell>
                    <TableCell>{fmtPct(r.dividendGrowthRate ?? null)}</TableCell>
                    <TableCell>{fmtPct(r.requiredReturn ?? null)}</TableCell>
                    <TableCell>{fmtInt(r.score ?? null)}</TableCell>
                    <TableCell>{r.category ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    );
  }, [loadingHistory, historyError, history, reloadHistory, valuation?.currency, variant]);

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded border border-rose-200 bg-rose-50 p-3 text-rose-700">
          {error}
        </div>
      ) : null}

      {summary}
      {howArrived}
      {suitability}

      <Separator />

      {historyCard}
    </div>
  );
}