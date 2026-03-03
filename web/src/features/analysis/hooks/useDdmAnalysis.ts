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
import { fetchDdmOutcome } from "@/features/analysis/services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Internal helper (unchanged from original)
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

type DdmData = {
  valuation:     DdmValuation;
  applicability: Applicability;
  dataQuality:   DataQuality;
  freshness?:    FreshnessInfo;
};

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Return contract is IDENTICAL to the original — no callers need changes.
//
// The original had a manual cacheRef + inflightRef to deduplicate concurrent
// requests and persist results across variant switches. React Query replaces
// all of that: each (symbol, variant) pair has its own cache entry with
// automatic request deduplication built in.
//
// Caching behaviour:
//   • First visit of a variant  → fetches, shows loading
//   • Switching variants        → instant if previously visited
//   • Navigate away+back        → instant (gcTime 30 min)
//   • recompute()               → force-invalidates and refetches current variant
// ─────────────────────────────────────────────────────────────────────────────

export function useDdmAnalysis(
  symbol:  string,
  variant: DdmVariant = "gordon",
): DdmState & {
  reload:    () => Promise<void>;
  recompute: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<DdmData, Error>({
    queryKey:  QK.ddm(currentSymbol, variant),
    queryFn:   async () => {
      const outcome = await fetchDdmOutcome(currentSymbol, variant);

      if (outcome.status === "ok") {
        const { payload } = outcome;
        const valuation    = payload.valuation     as unknown as DdmValuation;
        const applicability = payload.applicability as unknown as Applicability;
        const dataQuality  = payload.dataQuality   as unknown as DataQuality;
        return {
          valuation,
          applicability,
          dataQuality,
          freshness: toFreshnessInfoFromDataQuality(dataQuality),
        };
      }

      throw new Error(outcome.message || "Failed to compute DDM.");
    },
    enabled:   !!currentSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const recompute = useCallback(async (): Promise<void> => {
    if (!currentSymbol) return;
    await queryClient.invalidateQueries({ queryKey: QK.ddm(currentSymbol, variant) });
    await refetch();
  }, [currentSymbol, variant, queryClient, refetch]);

  // useMemo preserved from original to maintain referential stability
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
      reload:         recompute,
      recompute,
    }),
    [isPending, error, data, recompute],
  );
}