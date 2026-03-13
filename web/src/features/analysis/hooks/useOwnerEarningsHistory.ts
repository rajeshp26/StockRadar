// web/src/features/analysis/hooks/useOwnerEarningsHistory.ts
"use client";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { OwnerEarningsHistory } from "../types/analysis.types";
import { fetchOwnerEarningsHistory } from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export function useOwnerEarningsHistory(symbol: string): {
  loading:  boolean;
  error?:   string;
  history?: OwnerEarningsHistory;
  reload:   () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<OwnerEarningsHistory, Error>({
    queryKey:  QK.ownerEarningsHistory(currentSymbol),
    queryFn:   () => fetchOwnerEarningsHistory(currentSymbol),
    enabled:   !!currentSymbol,
    staleTime: STALE.HISTORY,
    gcTime:    GC.HISTORY,
    retry:     0, // non-critical — fetchOwnerEarningsHistory returns [] on failure
  });

  const reload = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: QK.ownerEarningsHistory(currentSymbol),
    });
    await refetch();
  }, [currentSymbol, queryClient, refetch]);

  return {
    loading: isPending,
    error:   error?.message,
    history: data,
    reload,
  };
}