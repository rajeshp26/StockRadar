"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { fetchDcfValuation } from "../services/analysis.service";
import type { DcfResponse } from "../types/analysis.types";
import { useDcfHistory } from "../hooks/useDcfHistory";

export function DcfPanel({ symbol }: { symbol: string }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DcfResponse | null>(null);
  const { history, loadingHistory, reloadHistory } = useDcfHistory(symbol);

  const load = useCallback(
    async (force = false) => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetchDcfValuation(symbol, { force });
        setData(resp);
      } catch (e: any) {
        setData(null);
        setError(e?.message ?? "Failed to load DCF valuation");
      } finally {
        setLoading(false);
      }
    },
    [symbol]
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  // Pull these up so hooks below can reference safely
  const valuation = data?.valuation ?? null;
  const applicability = data?.applicability ?? null;

  // ============================
  // Priority 6.2 — FE Guardrails
  // ============================
  // IMPORTANT: must be declared before any early returns to preserve hook order.
  const invariantIssue = useMemo(() => {
    const issues: string[] = [];

    // If valuation doesn't exist yet (loading/error/not computed), do not enforce invariants.
    if (!valuation) return issues;

    const {
      forecastYears,
      forecastFcf,
      pvFcf,
      discountFactors,
      sensitivityScenarios,
    } = valuation;

    if (!Number.isFinite(forecastYears) || forecastYears <= 0) {
      issues.push(`forecastYears is invalid (${String(forecastYears)}).`);
      return issues;
    }

    if (!Array.isArray(forecastFcf) || forecastFcf.length !== forecastYears) {
      issues.push(
        `forecastFcf length (${forecastFcf?.length ?? "n/a"}) does not match forecastYears (${forecastYears}).`
      );
    }

    if (!Array.isArray(pvFcf) || pvFcf.length !== forecastYears) {
      issues.push(
        `pvFcf length (${pvFcf?.length ?? "n/a"}) does not match forecastYears (${forecastYears}).`
      );
    }

    if (discountFactors && Array.isArray(discountFactors) && discountFactors.length !== forecastYears) {
      issues.push(
        `discountFactors length (${discountFactors.length}) does not match forecastYears (${forecastYears}).`
      );
    }

    if (sensitivityScenarios) {
      const rLen = sensitivityScenarios.discountRates?.length ?? 0;
      const gLen = sensitivityScenarios.terminalGrowthRates?.length ?? 0;
      const m = sensitivityScenarios.intrinsicValuePerShareMatrix;

      if (!Array.isArray(m) || m.length !== rLen) {
        issues.push(
          `sensitivity matrix rows (${m?.length ?? "n/a"}) does not match discountRates length (${rLen}).`
        );
      } else {
        const badRow = m.find((row) => !Array.isArray(row) || row.length !== gLen);
        if (badRow) {
          issues.push(`sensitivity matrix columns do not match terminalGrowthRates length (${gLen}).`);
        }
      }
    }

    return issues;
  }, [valuation]);

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Discounted Cash Flow (DCF)</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-500">Loading…</CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Discounted Cash Flow (DCF)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-rose-600">{error}</div>
          <Button onClick={() => void load(true)}>Retry / Recompute</Button>
        </CardContent>
      </Card>
    );
  }



  if (!valuation) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Discounted Cash Flow (DCF)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="text-sm text-slate-500">
            DCF valuation is not available for this company yet.
          </div>
          <Button onClick={() => void load(true)}>Compute DCF</Button>
        </CardContent>
      </Card>
    );
  }

  const {
    forecastYears,
    forecastFcf,
    pvFcf,
    discountFactors,
    terminalValue,
    pvTerminalValue,
    enterpriseValue,
    netDebtUsed,
    equityValue,
    sharesOutstanding,
    intrinsicValuePerShare,
    currentPrice,
    upsideDownsidePct,
    waccUsed,
    terminalMethod,
    terminalGrowthRateUsed,
    cashFlowNPlus1,
    baseFcf,
    baseFcfFiscalYear,
    sensitivityScenarios,
  } = valuation;

  

  // If invariants are broken, show a visible banner and stop rendering the detailed tables.
  // This prevents misleading output and avoids runtime table errors.
  if (invariantIssue.length > 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Discounted Cash Flow (DCF)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-rose-700">
            <div className="font-medium">DCF output is inconsistent.</div>
            <div className="mt-1 text-xs">
              This usually indicates a partial/invalid computation snapshot. Please recompute to regenerate a consistent run.
            </div>
            <ul className="mt-2 list-disc pl-5 text-xs">
              {invariantIssue.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          </div>
          <Button onClick={() => void load(true)}>Recompute</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Discounted Cash Flow (DCF)</CardTitle>
      </CardHeader>

      <CardContent className="space-y-6 text-sm">
        {/* ================= SUMMARY ================= */}
        <section className="space-y-2">
          <div className="flex items-center gap-3">
            <div className="font-medium">Intrinsic Value / Share:</div>
            <div>
              {intrinsicValuePerShare !== undefined && intrinsicValuePerShare !== null
                ? intrinsicValuePerShare.toFixed(2)
                : "—"}
            </div>
            {upsideDownsidePct !== null && upsideDownsidePct !== undefined && (
              <Badge variant={upsideDownsidePct >= 0 ? "default" : "destructive"}>
                {(upsideDownsidePct * 100).toFixed(1)}%
              </Badge>
            )}
          </div>

          <div>
            <span className="font-medium">Current Price:</span>{" "}
            {currentPrice !== null && currentPrice !== undefined
              ? currentPrice.toFixed(2)
              : "—"}
          </div>

          <div>
            <span className="font-medium">WACC:</span>{" "}
            {(waccUsed * 100).toFixed(2)}%
          </div>

          <div>
            <span className="font-medium">Terminal Method:</span>{" "}
            {terminalMethod}
          </div>
        </section>

        <Separator />

        {/* ================= HOW WE ARRIVED HERE ================= */}
        <section className="space-y-4">
          <h4 className="font-semibold">How We Arrived Here</h4>

          {baseFcf !== null && baseFcf !== undefined && (
            <div className="text-xs text-slate-500">
              Base FCF used: {baseFcf.toFixed(2)}
              {baseFcfFiscalYear && ` (FY ${baseFcfFiscalYear})`}
            </div>
          )}

          {/* Forecast table */}
          <div className="overflow-x-auto">
            <table className="min-w-full border text-xs">
              <thead className="bg-slate-50">
                <tr>
                  <th className="border px-2 py-1 text-left">Year</th>
                  <th className="border px-2 py-1 text-right">FCF</th>
                  <th className="border px-2 py-1 text-right">Discount Factor</th>
                  <th className="border px-2 py-1 text-right">PV of FCF</th>
                </tr>
              </thead>
              <tbody>
                {forecastFcf.map((cf, i) => (
                  <tr key={i}>
                    <td className="border px-2 py-1">{i + 1}</td>
                    <td className="border px-2 py-1 text-right">
                      {cf.toFixed(2)}
                    </td>
                    <td className="border px-2 py-1 text-right">
                      {discountFactors?.[i]?.toFixed(4) ?? "—"}
                    </td>
                    <td className="border px-2 py-1 text-right">
                      {pvFcf[i]?.toFixed(2) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Terminal */}
          <div className="space-y-1">
            <div>
              <span className="font-medium">Terminal Value:</span>{" "}
              {terminalValue !== null && terminalValue !== undefined
                ? terminalValue.toFixed(2)
                : "—"}
            </div>
            <div>
              <span className="font-medium">PV of Terminal Value:</span>{" "}
              {pvTerminalValue !== null && pvTerminalValue !== undefined
                ? pvTerminalValue.toFixed(2)
                : "—"}
            </div>

            {terminalGrowthRateUsed !== null && terminalGrowthRateUsed !== undefined && (
              <div className="text-xs text-slate-500">
                Terminal growth (g): {(terminalGrowthRateUsed * 100).toFixed(2)}%
                {cashFlowNPlus1 !== null && cashFlowNPlus1 !== undefined && (
                  <> · CFₙ₊₁ = {cashFlowNPlus1.toFixed(2)}</>
                )}
              </div>
            )}
          </div>

          {/* Bridge */}
          <div className="space-y-1">
            <div>
              <span className="font-medium">Enterprise Value:</span>{" "}
              {enterpriseValue?.toFixed(2) ?? "—"}
            </div>
            <div>
              <span className="font-medium">Net Debt:</span>{" "}
              {netDebtUsed?.toFixed(2) ?? "—"}
            </div>
            <div>
              <span className="font-medium">Equity Value:</span>{" "}
              {equityValue?.toFixed(2) ?? "—"}
            </div>
            <div>
              <span className="font-medium">Shares Outstanding:</span>{" "}
              {sharesOutstanding?.toFixed(2) ?? "—"}
            </div>
          </div>
        </section>

        <Separator />

        {/* ================= SUITABILITY ================= */}
        {applicability && (
          <section className="space-y-3">
            <h4 className="font-semibold">DCF Suitability</h4>

            <div className="flex items-center gap-3">
              <Badge>
                Score: {applicability.score} / 100
              </Badge>
              <Badge variant="outline">
                {applicability.category}
              </Badge>
            </div>

            <ul className="space-y-2">
              {applicability.flags.map((f, idx) => (
                <li key={idx} className="text-xs">
                  <span className="font-medium">{f.code}</span>: {f.message}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* ================= SENSITIVITY (r x g) ================= */}
        <Separator />
        <section className="space-y-3">
          <h4 className="font-semibold">Sensitivity (Discount Rate × Terminal Growth)</h4>
          {!sensitivityScenarios ? (
            <div className="text-xs text-slate-500">
              Sensitivity grid not available for this run.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full border text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="border px-2 py-1 text-left">r \ g</th>
                    {sensitivityScenarios.terminalGrowthRates.map((g, i) => (
                      <th key={i} className="border px-2 py-1 text-right">
                        {(g * 100).toFixed(1)}%
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sensitivityScenarios.discountRates.map((r, ri) => (
                    <tr key={ri}>
                      <td className="border px-2 py-1">
                        {(r * 100).toFixed(1)}%
                      </td>
                      {sensitivityScenarios.intrinsicValuePerShareMatrix[ri].map((v, gi) => (
                        <td key={gi} className="border px-2 py-1 text-right">
                          {typeof v === "number" ? v.toFixed(2) : "—"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {sensitivityScenarios.currency && (
                <div className="text-[11px] text-slate-500 pt-1">
                  Values are intrinsic value per share ({sensitivityScenarios.currency})
                </div>
              )}
            </div>
          )}
        </section>

        <div className="pt-2">
          <Button onClick={() => void load(true)}>Recompute</Button>
        </div>

        {/* ================= HISTORY ================= */}
        <Separator />
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold">History</h4>
            <Button variant="outline" size="sm" onClick={() => void reloadHistory()}>
              Refresh History
            </Button>
          </div>

          {loadingHistory ? (
            <div className="text-xs text-slate-500">Loading history…</div>
          ) : history.items.length === 0 ? (
            <div className="text-xs text-slate-500">
              No previous DCF calculations found.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full border text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="border px-2 py-1 text-left">Run At</th>
                    <th className="border px-2 py-1 text-left">Method</th>
                    <th className="border px-2 py-1 text-right">Intrinsic / Share</th>
                    <th className="border px-2 py-1 text-right">WACC</th>
                    <th className="border px-2 py-1 text-right">Score</th>
                    <th className="border px-2 py-1 text-left">Category</th>
                  </tr>
                </thead>
                <tbody>
                  {history.items.map((it, idx) => (
                    <tr key={idx}>
                      <td className="border px-2 py-1">
                        {it.runAt ? new Date(it.runAt).toLocaleString() : "—"}
                      </td>
                      <td className="border px-2 py-1">
                        {it.terminalMethod ?? "—"}
                      </td>
                      <td className="border px-2 py-1 text-right">
                        {typeof it.intrinsicValuePerShare === "number"
                          ? it.intrinsicValuePerShare.toFixed(2)
                          : "—"}
                      </td>
                      <td className="border px-2 py-1 text-right">
                        {typeof it.waccUsed === "number"
                          ? `${(it.waccUsed * 100).toFixed(2)}%`
                          : "—"}
                      </td>
                      <td className="border px-2 py-1 text-right">
                        {typeof it.score === "number" ? it.score : "—"}
                      </td>
                      <td className="border px-2 py-1">
                        {it.category ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}