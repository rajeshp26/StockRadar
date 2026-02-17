"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { fetchDcfValuation } from "../services/analysis.service";
import type { DcfResponse } from "../types/analysis.types";
import { useDcfHistory } from "../hooks/useDcfHistory";

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

export function DcfPanel({ symbol }: { symbol: string }) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DcfResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  const { loading: loadingHistory, error: historyError, history, reload: reloadHistory } =
    useDcfHistory(symbol);

  const load = useCallback(
    async (force = false) => {
      setLoading(true);
      setError(null);
      try {
        setData(await fetchDcfValuation(symbol, { force }));
      } catch (e: any) {
        setError(e?.message ?? "Failed to load DCF");
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [symbol]
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await load(true);
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [load, reloadHistory]);

  const v = data?.valuation;
  const applicability = data?.applicability;
  const curr = v?.currency ?? "USD";

  const historyCard = useMemo(() => {
    const items = history?.items ?? [];

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
                  <TableHead>Terminal</TableHead>
                  <TableHead>Intrinsic / Share</TableHead>
                  <TableHead>WACC</TableHead>
                  <TableHead>Enterprise</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Category</TableHead>
                </TableRow>
              </TableHeader>

              <TableBody>
                {items.map((r, idx) => (
                  <TableRow key={`${r.runAt}-${idx}`}>
                    <TableCell>{fmtDateTime(r.runAt)}</TableCell>
                    <TableCell>{r.terminalMethod ?? "—"}</TableCell>
                    <TableCell>{fmtCurrency(r.intrinsicValuePerShare ?? null, curr)}</TableCell>
                    <TableCell>{fmtPct(r.waccUsed ?? null)}</TableCell>
                    <TableCell>{fmtCurrency(r.enterpriseValue ?? null, curr)}</TableCell>
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
  }, [history, loadingHistory, historyError, reloadHistory, curr]);

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded border border-rose-200 bg-rose-50 p-3 text-rose-700">
          {error}
        </div>
      ) : null}

      {/* Summary */}
      <Card className="glass rounded-3xl border border-white/5 text-white relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-indigo-500 to-transparent opacity-50" />
        <CardHeader className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <CardTitle>Discounted Cash Flow (DCF)</CardTitle>
            <Button onClick={handleRecompute} disabled={loading || recomputing}>
              {recomputing ? "Recomputing…" : "Recompute"}
            </Button>
          </div>
          <div className="text-sm text-slate-400">
            Cash‑flow based intrinsic value with full transparency.
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
              <Metric label="Intrinsic Value / Share" value={fmtCurrency(v?.intrinsicValuePerShare ?? null, curr)} />
              <Metric label="Current Price" value={fmtCurrency(v?.currentPrice ?? null, curr)} />
              <Metric label="Upside / Downside" value={fmtPct(v?.upsideDownsidePct ?? null)} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* How we arrived */}
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
            <div className="grid md:grid-cols-3 gap-4">
              <Metric label="Base FCF" value={fmtCurrency(v?.baseFcf ?? null, curr)} />
              <Metric label="Forecast Years" value={fmtInt(v?.forecastYears ?? null)} />
              <Metric label="WACC" value={fmtPct(v?.waccUsed ?? null)} />

              <Metric label="Terminal Method" value={v?.terminalMethod ?? "—"} />
              <Metric label="Enterprise Value" value={fmtCurrency(v?.enterpriseValue ?? null, curr)} />
              <Metric label="Equity Value" value={fmtCurrency(v?.equityValue ?? null, curr)} />

              <Metric label="Net Debt" value={fmtCurrency(v?.netDebtUsed ?? null, curr)} />
              <Metric label="Shares Outstanding" value={fmtInt(v?.sharesOutstanding ?? null)} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Suitability */}
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

      <Separator />

      {historyCard}
    </div>
  );
}