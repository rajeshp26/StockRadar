// web/src/features/analysis/hooks/useOwnerEarningsAnalysis.ts
"use client";
import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  OwnerEarningsState,
  OwnerEarningsValuation,
  Applicability,
  DataQuality,
  FreshnessInfo,
} from "../types/analysis.types";
import { fetchOwnerEarningsOutcome } from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Internal helper — mirrors useDdmAnalysis pattern exactly
// ─────────────────────────────────────────────────────────────────────────────
function toFreshnessInfo(dq?: DataQuality): FreshnessInfo | undefined {
  const lastComputedAt = (dq?.freshnessDays as any)?.lastComputedAt;
  if (!lastComputedAt || typeof lastComputedAt !== "string") return undefined;
  const d = new Date(lastComputedAt);
  if (Number.isNaN(d.getTime())) return undefined;
  return {
    lastEvaluatedIso:     lastComputedAt,
    lastEvaluatedDisplay: d.toLocaleString(),
  };
}

type OeData = {
  valuation:     OwnerEarningsValuation;
  applicability: Applicability;
  dataQuality:   DataQuality;
  freshness?:    FreshnessInfo;
};

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Caching behaviour:
//   • First visit  → fetches, shows loading
//   • Navigate away+back → instant (gcTime 30 min)
//   • recompute()  → invalidates + refetches
// ─────────────────────────────────────────────────────────────────────────────
export function useOwnerEarningsAnalysis(
  symbol: string
): OwnerEarningsState & {
  reload:    () => Promise<void>;
  recompute: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<OeData, Error>({
    queryKey:  QK.ownerEarnings(currentSymbol),
    queryFn:   async () => {
      const outcome = await fetchOwnerEarningsOutcome(currentSymbol);
      if (outcome.status === "ok") {
        const { payload } = outcome;
        return {
          valuation:    payload.valuation    as unknown as OwnerEarningsValuation,
          applicability: payload.applicability as unknown as Applicability,
          dataQuality:  payload.dataQuality  as unknown as DataQuality,
          freshness:    toFreshnessInfo(payload.dataQuality as unknown as DataQuality),
        };
      }
      throw new Error(outcome.message || "Failed to compute Owner Earnings.");
    },
    enabled:   !!currentSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const recompute = useCallback(async (): Promise<void> => {
    if (!currentSymbol) return;
    await queryClient.invalidateQueries({ queryKey: QK.ownerEarnings(currentSymbol) });
    await refetch();
  }, [currentSymbol, queryClient, refetch]);

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
    [isPending, error, data, recompute]
  );
}