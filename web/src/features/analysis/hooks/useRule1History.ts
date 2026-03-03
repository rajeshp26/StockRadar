// web/src/features/analysis/hooks/useRule1History.ts
"use client";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchRule1History } from "@/features/analysis/services/analysis.service";
import type { Rule1History } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Return contract is IDENTICAL to the original — no callers need changes.
//
// History data changes only when the backend recomputes a valuation,
// which is rare. 15-minute stale time + 60-minute GC is intentionally
// generous — history tables should almost always load from cache.
//
// retry: 0 — history is non-critical and the service already returns
// an empty {items:[]} on failure, so hammering a failed endpoint adds no value.
// ─────────────────────────────────────────────────────────────────────────────

export function useRule1History(symbol: string): {
  loading:  boolean;
  error?:   string;
  history?: Rule1History;
  reload:   () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<Rule1History, Error>({
    queryKey:  QK.rule1History(currentSymbol),
    queryFn:   () => fetchRule1History(currentSymbol),
    enabled:   !!currentSymbol,
    staleTime: STALE.HISTORY,
    gcTime:    GC.HISTORY,
    retry:     0,   // non-critical; service returns empty list on failure
  });

  const reload = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: QK.rule1History(currentSymbol) });
    await refetch();
  }, [currentSymbol, queryClient, refetch]);

  return {
    loading: isPending,
    error:   error?.message,
    history: data,
    reload,
  };
}