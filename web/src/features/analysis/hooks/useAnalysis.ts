// web/src/features/analysis/hooks/useAnalysis.ts
"use client";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { formatTimestamp } from "@/lib/time";
import type {
  AnalysisState,
  Rule1Valuation as CamelValuation,
  DataQuality as UiDataQuality,
  Applicability as UiApplicability,
  FreshnessInfo,
} from "../types/analysis.types";
import {
  fetchRule1Cached,
  fetchRule1Outcome,
} from "@/features/analysis/services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function toFreshnessInfoFromDataQuality(dq?: UiDataQuality): FreshnessInfo | undefined {
  const lastComputedAt = (dq?.freshnessDays as any)?.lastComputedAt;
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;
  // Validate the string is parseable before committing to it
  const probe = new Date(lastComputedAt.endsWith("Z") ? lastComputedAt : lastComputedAt + "Z");
  if (Number.isNaN(probe.getTime())) return undefined;
   return {
    lastEvaluatedIso:     lastComputedAt,
    // "absolute" strategy: always shows a specific date+time in the user's
    // local timezone — never a relative "ago" string — so the user can
    // reason about how fresh the valuation data is.
    lastEvaluatedDisplay: formatTimestamp(lastComputedAt, "absolute") ?? lastComputedAt,
  };
}

type Rule1Data = {
  valuation:     CamelValuation;
  applicability: UiApplicability;
  dataQuality:   UiDataQuality;
  freshness?:    FreshnessInfo;
  notComputed?:  boolean;  // true when backend returns 404 (never run)
};

// ─────────────────────────────────────────────────────────────────────────────
// queryFn — exported so the analysis page can use the same function for
// prefetchQuery without duplicating the transformation logic.
// ─────────────────────────────────────────────────────────────────────────────

export async function rule1QueryFn(symbol: string): Promise<Rule1Data> {
  const outcome = await fetchRule1Cached(symbol);

  if (outcome.status === "not_computed") {
    // Return a sentinel value rather than throwing.
    // The component renders a "Run Computation" CTA instead of an error state.
    return {
      valuation:    {} as CamelValuation,
      applicability: {} as UiApplicability,
      dataQuality:  {} as UiDataQuality,
      notComputed:  true,
    };
  }

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

  throw new Error(outcome.message || "Failed to load valuation.");
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Behaviour:
//   queryFn   → GET (pure cache read, ~50ms)
//   recompute → POST (full gate logic, only on explicit user action)
//
// First tab click: instant if prefetchAllValuations() already ran on page load.
// ─────────────────────────────────────────────────────────────────────────────

export function useAnalysis(
  symbol: string,
  opts: { analytics?: any } = {},
): AnalysisState & {
  reload:      () => Promise<void>;
  recompute:   () => Promise<void>;
  notComputed: boolean;
} {
  const { analytics }  = opts;
  const currentSymbol  = (symbol ?? "").toUpperCase();
  const queryClient    = useQueryClient();

  const { data, isPending, error } = useQuery<Rule1Data, Error>({
    queryKey:  QK.rule1(currentSymbol),
    queryFn:   () => rule1QueryFn(currentSymbol),
    enabled:   !!currentSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  /**
   * recompute
   * Sends POST to backend (runs gate logic, triggers recompute if stale),
   * then writes the fresh payload directly into the React Query cache.
   * The component re-renders with new data without an extra round-trip.
   */
  const recompute = useCallback(async (): Promise<void> => {
    if (!currentSymbol) return;
    const outcome = await fetchRule1Outcome(currentSymbol);
    if (outcome.status === "ok") {
      const { payload } = outcome;
      const valuation    = payload.valuation     as unknown as CamelValuation;
      const applicability = payload.applicability as unknown as UiApplicability;
      const dataQuality  = payload.dataQuality   as unknown as UiDataQuality;
      queryClient.setQueryData<Rule1Data>(QK.rule1(currentSymbol), {
        valuation,
        applicability,
        dataQuality,
        freshness: toFreshnessInfoFromDataQuality(dataQuality),
        notComputed: false,
      });
    } else {
      analytics?.onError?.(currentSymbol, outcome.message);
      throw new Error(outcome.message);
    }
  }, [currentSymbol, queryClient, analytics]);

  return {
    loading:        isPending,
    loadingHistory: false,
    error:          error?.message,
    valuation:      data?.valuation,
    applicability:  data?.applicability,
    dataQuality:    data?.dataQuality,
    history:        undefined,
    freshness:      data?.freshness,
    notComputed:    data?.notComputed ?? false,
    reload:         recompute,
    recompute,
  };
}