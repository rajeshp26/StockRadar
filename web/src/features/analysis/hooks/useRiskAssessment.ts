"use client";

import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { fetchRiskCached, fetchRiskAssessment, fetchRiskAiNarrative } from "../services/analysis.service";
import type { RiskAssessmentResponse } from "../types/analysis.types";

export type RiskQueryData =
  | { notComputed: true }
  | (RiskAssessmentResponse & { notComputed: false });

export async function riskQueryFn(symbol: string): Promise<RiskQueryData> {
  const outcome = await fetchRiskCached(symbol);
  if (outcome.status === "not_computed") return { notComputed: true };
  if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
  throw new Error(outcome.message || "Failed to load risk assessment.");
}

export function useRiskAssessment(symbol: string) {
  const upperSymbol = (symbol ?? "").toUpperCase();
  const queryClient = useQueryClient();

  const { data, isPending, error } = useQuery<RiskQueryData, Error>({
    queryKey: QK.riskAssessment(upperSymbol),
    queryFn: () => riskQueryFn(upperSymbol),
    enabled: !!upperSymbol,
    staleTime: STALE.VALUATION,
    gcTime: GC.VALUATION,
    retry: 1,
  });

  const recompute = useCallback(async (): Promise<void> => {
    if (!upperSymbol) return;
    const fresh = await fetchRiskAssessment(upperSymbol, { force: true });
    queryClient.setQueryData<RiskQueryData>(QK.riskAssessment(upperSymbol), {
      ...fresh,
      notComputed: false,
    });
  }, [upperSymbol, queryClient]);

  const generateAi = useCallback(async (): Promise<void> => {
    if (!upperSymbol) return;
    const result = await fetchRiskAiNarrative(upperSymbol);
    queryClient.setQueryData<RiskQueryData>(QK.riskAssessment(upperSymbol), (old) => {
      if (!old || old.notComputed) return old;
      return {
        ...old,
        ai_narrative: {
          narrative: result.narrative,
          model: result.model,
          generated_at: new Date().toISOString(),
        },
        notComputed: false,
      };
    });
  }, [upperSymbol, queryClient]);

  const notComputed = data?.notComputed ?? false;
  const responseData = notComputed ? null : (data as RiskAssessmentResponse & { notComputed: false }) ?? null;

  return {
    data: responseData,
    loading: isPending,
    error: error?.message ?? null,
    notComputed,
    recompute,
    generateAi,
  };
}
