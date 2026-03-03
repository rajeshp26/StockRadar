// web/src/features/analysis/hooks/useAnalysis.ts
"use client";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  AnalysisState,
  Rule1Valuation as CamelValuation,
  DataQuality as UiDataQuality,
  Applicability as UiApplicability,
  FreshnessInfo,
} from "../types/analysis.types";
import { fetchRule1Outcome } from "@/features/analysis/services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Internal helpers (unchanged from original)
// ─────────────────────────────────────────────────────────────────────────────

function toFreshnessInfoFromDataQuality(dq?: UiDataQuality): FreshnessInfo | undefined {
  const lastComputedAt = (dq?.freshnessDays as any)?.lastComputedAt;
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;
  const d = new Date(lastComputedAt);
  if (Number.isNaN(d.getTime())) return undefined;
  return {
    lastEvaluatedIso:     lastComputedAt,
    lastEvaluatedDisplay: d.toLocaleString(),
  };
}

type Rule1Data = {
  valuation:     CamelValuation;
  applicability: UiApplicability;
  dataQuality:   UiDataQuality;
  freshness?:    FreshnessInfo;
};

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Return contract is IDENTICAL to the original — no callers need changes.
//
// Caching behaviour:
//   • First visit to a symbol  → fetches, shows loading state
//   • Tab switch (overview→rule1→dcf) → instant (cache hit per symbol+method)
//   • Navigate away and back   → instant (gcTime keeps data in memory 30 min)
//   • recompute()              → forces fresh fetch regardless of stale time
// ─────────────────────────────────────────────────────────────────────────────

export function useAnalysis(
  symbol: string,
  opts: { analytics?: any } = {},
): AnalysisState & {
  reload:    () => Promise<void>;
  recompute: () => Promise<void>;
} {
  const { analytics }   = opts;
  const currentSymbol   = (symbol ?? "").toUpperCase();
  const queryClient     = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<Rule1Data, Error>({
    queryKey:  QK.rule1(currentSymbol),
    queryFn:   async () => {
      const outcome = await fetchRule1Outcome(currentSymbol);

      if (outcome.status === "ok") {
        const { payload } = outcome;
        const valuation    = payload.valuation     as unknown as CamelValuation;
        const applicability = payload.applicability as unknown as UiApplicability;
        const dataQuality  = payload.dataQuality   as unknown as UiDataQuality;
        return {
          valuation,
          applicability,
          dataQuality,
          freshness: toFreshnessInfoFromDataQuality(dataQuality),
        };
      }

      const msg = outcome.message || "Failed to compute valuation.";
      analytics?.onError?.(currentSymbol, msg);
      throw new Error(msg);
    },
    enabled:   !!currentSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  /**
   * recompute / reload
   * Invalidates the cache entry (marks stale) then immediately refetches.
   * Used by "Recalculate" buttons in the analysis panels.
   */
  const recompute = useCallback(async (): Promise<void> => {
    if (!currentSymbol) return;
    await queryClient.invalidateQueries({ queryKey: QK.rule1(currentSymbol) });
    await refetch();
  }, [currentSymbol, queryClient, refetch]);

  // ── Return shape matches original exactly ────────────────────────────────
  return {
    loading:        isPending,
    loadingHistory: false,          // history is a separate hook; always false here
    error:          error?.message,
    valuation:      data?.valuation,
    applicability:  data?.applicability,
    dataQuality:    data?.dataQuality,
    history:        undefined,
    freshness:      data?.freshness,
    reload:         recompute,
    recompute,
  };
}