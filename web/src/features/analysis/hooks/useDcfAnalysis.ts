// web/src/features/analysis/hooks/useDcfAnalysis.ts
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchDcfCached,
  fetchDcfValuation,
} from "../services/analysis.service";
import type { DcfResponse } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// queryFn — exported for use in prefetchAllValuations()
// ─────────────────────────────────────────────────────────────────────────────

export type DcfQueryData =
  | { notComputed: true }
  | (DcfResponse & { notComputed: false });

export async function dcfQueryFn(symbol: string): Promise<DcfQueryData> {
  const outcome = await fetchDcfCached(symbol);
  if (outcome.status === "not_computed") return { notComputed: true };
  if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
  throw new Error(outcome.message || "Failed to load DCF valuation.");
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────

export function useDcfAnalysis(symbol: string) {
  const upperSymbol = (symbol ?? "").toUpperCase();
  const queryClient = useQueryClient();

  const { data, isPending, error } = useQuery<DcfQueryData, Error>({
    queryKey:  QK.dcf(upperSymbol),
    queryFn:   () => dcfQueryFn(upperSymbol),
    enabled:   !!upperSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  /**
   * recompute
   * POST with force=true → full recompute → update cache in-place.
   */
  const recompute = useCallback(async (): Promise<void> => {
    if (!upperSymbol) return;
    const fresh = await fetchDcfValuation(upperSymbol, { force: true });
    queryClient.setQueryData<DcfQueryData>(QK.dcf(upperSymbol), {
      ...fresh,
      notComputed: false,
    });
  }, [upperSymbol, queryClient]);

  const notComputed = data?.notComputed ?? false;
  const responseData = notComputed ? null : (data as DcfResponse & { notComputed: false }) ?? null;

  return {
    data:        responseData,
    loading:     isPending,
    error:       error?.message ?? null,
    notComputed,
    recompute,
  };
}