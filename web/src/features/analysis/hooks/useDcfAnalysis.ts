// web/src/features/analysis/hooks/useDcfAnalysis.ts
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchDcfValuation } from "../services/analysis.service";
import type { DcfResponse } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Return contract is IDENTICAL to the original — no callers need changes.
//
// Caching behaviour:
//   • First visit       → fetches, shows loading
//   • Navigate away+back → instant (gcTime 30 min)
//   • recompute()       → calls backend with force=true, updates cache in-place
//                         (no refetch round-trip needed — result applied directly)
// ─────────────────────────────────────────────────────────────────────────────

export function useDcfAnalysis(symbol: string) {
  const upperSymbol = (symbol ?? "").toUpperCase();
  const queryClient = useQueryClient();

  const { data, isPending, error } = useQuery<DcfResponse, Error>({
    queryKey:  QK.dcf(upperSymbol),
    queryFn:   () => fetchDcfValuation(upperSymbol, { force: false }),
    enabled:   !!upperSymbol,
    staleTime: STALE.VALUATION,
    gcTime:    GC.VALUATION,
    retry:     1,
  });

  /**
   * recompute
   * Sends force=true to the backend (triggers a full recompute, not cached result),
   * then writes the fresh payload directly into the React Query cache.
   * The component re-renders with new data without an extra network round-trip.
   */
  const recompute = useCallback(async (): Promise<void> => {
    if (!upperSymbol) return;
    const fresh = await fetchDcfValuation(upperSymbol, { force: true });
    queryClient.setQueryData<DcfResponse>(QK.dcf(upperSymbol), fresh);
  }, [upperSymbol, queryClient]);

  return {
    data:    data ?? null,
    loading: isPending,
    error:   error?.message ?? null,
    recompute,
  };
}