// web/src/features/analysis/hooks/useResidualIncomeAnalysis.ts
"use client";
import { useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ResidualIncomeState,
  ResidualIncomeValuation,
  Applicability,
  DataQuality,
  FreshnessInfo,
} from "../types/analysis.types";
import { fetchResidualIncomeOutcome } from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Internal helper
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

type RiData = {
  valuation:     ResidualIncomeValuation;
  applicability: Applicability;
  dataQuality:   DataQuality;
  freshness?:    FreshnessInfo;
};

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────
export function useResidualIncomeAnalysis(
  symbol: string
): ResidualIncomeState & {
  reload:    () => Promise<void>;
  recompute: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<RiData, Error>({
    queryKey:  QK.residualIncome(currentSymbol),
    queryFn:   async () => {
      const outcome = await fetchResidualIncomeOutcome(currentSymbol);
      if (outcome.status === "ok") {
        const { payload } = outcome;
        return {
          valuation:    payload.valuation    as unknown as ResidualIncomeValuation,
          applicability: payload.applicability as unknown as Applicability,
          dataQuality:  payload.dataQuality  as unknown as DataQuality,
          freshness:    toFreshnessInfo(payload.dataQuality as unknown as DataQuality),
        };
      }
      throw new Error(outcome.message || "Failed to compute Residual Income.");
    },
    enabled:   !!currentSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  const recompute = useCallback(async (): Promise<void> => {
    if (!currentSymbol) return;
    await queryClient.invalidateQueries({ queryKey: QK.residualIncome(currentSymbol) });
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