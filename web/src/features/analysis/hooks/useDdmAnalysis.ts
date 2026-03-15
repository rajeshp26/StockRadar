// web/src/features/analysis/hooks/useDdmAnalysis.ts
"use client";
import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  DdmState,
  DdmValuation,
  Applicability,
  DataQuality,
  FreshnessInfo,
  DdmVariant,
} from "../types/analysis.types";
import {
  fetchDdmCached,
  fetchDdmOutcome,
} from "@/features/analysis/services/analysis.service";
import { QK }    from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Helper
// ─────────────────────────────────────────────────────────────────────────────

function toFreshnessInfoFromDataQuality(dq?: DataQuality): FreshnessInfo | undefined {
  const lastComputedAt = (dq?.freshnessDays as any)?.lastComputedAt;
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;
  const d = new Date(lastComputedAt);
  if (Number.isNaN(d.getTime())) return undefined;
  return {
    lastEvaluatedIso:     lastComputedAt,
    lastEvaluatedDisplay: d.toLocaleString(),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Internal data shape (includes notComputed sentinel)
// ─────────────────────────────────────────────────────────────────────────────

type DdmData = {
  valuation?:     DdmValuation;
  applicability?: Applicability;
  dataQuality?:   DataQuality;
  freshness?:     FreshnessInfo;
  notComputed?:   boolean;
};

// ─────────────────────────────────────────────────────────────────────────────
// queryFn — exported so prefetch-valuations.ts and useValuationOverview share it
// ─────────────────────────────────────────────────────────────────────────────

export async function ddmQueryFn(
  symbol:  string,
  variant: DdmVariant,
): Promise<DdmData> {
  const outcome = await fetchDdmCached(symbol, variant);

  if (outcome.status === "not_computed") {
    return { notComputed: true };
  }

  if (outcome.status === "ok") {
    const { payload } = outcome;
    const valuation    = payload.valuation     as unknown as DdmValuation;
    const applicability = payload.applicability as unknown as Applicability;
    const dataQuality  = payload.dataQuality   as unknown as DataQuality;
    return {
      valuation,
      applicability,
      dataQuality,
      freshness:    toFreshnessInfoFromDataQuality(dataQuality),
      notComputed:  false,
    };
  }

  throw new Error(outcome.message || "Failed to load DDM valuation.");
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// queryFn  → GET (pure cache read, ~50ms)
// recompute → POST (gate logic, only on explicit user action)
//
// Return contract is IDENTICAL to the original — no callers need changes.
// ─────────────────────────────────────────────────────────────────────────────

export function useDdmAnalysis(
  symbol:  string,
  variant: DdmVariant = "gordon",
): DdmState & {
  reload:      () => Promise<void>;
  recompute:   () => Promise<void>;
  notComputed: boolean;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error } = useQuery<DdmData, Error>({
    queryKey:  QK.ddm(currentSymbol, variant),
    queryFn:   () => ddmQueryFn(currentSymbol, variant),
    enabled:   !!currentSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  /**
   * recompute
   * POST → gate logic + potential recompute → write fresh payload into cache.
   * Does not trigger an extra refetch round-trip.
   */
  const recompute = useCallback(async (): Promise<void> => {
    if (!currentSymbol) return;
    const outcome = await fetchDdmOutcome(currentSymbol, variant);
    if (outcome.status === "ok") {
      const { payload } = outcome;
      const valuation    = payload.valuation     as unknown as DdmValuation;
      const applicability = payload.applicability as unknown as Applicability;
      const dataQuality  = payload.dataQuality   as unknown as DataQuality;
      queryClient.setQueryData<DdmData>(QK.ddm(currentSymbol, variant), {
        valuation,
        applicability,
        dataQuality,
        freshness:   toFreshnessInfoFromDataQuality(dataQuality),
        notComputed: false,
      });
      // Invalidate overview so AI recommendation regenerates with fresh data
      queryClient.invalidateQueries({ queryKey: QK.overview(currentSymbol) });
    } else {
      throw new Error(outcome.message || "Failed to compute DDM.");
    }
  }, [currentSymbol, variant, queryClient]);

  return useMemo(
    () => ({
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
    }),
    [isPending, error, data, recompute],
  );
}