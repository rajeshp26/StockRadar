// web/src/features/analysis/hooks/useResidualIncomeHistory.ts
"use client";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { ResidualIncomeHistory } from "../types/analysis.types";
import { fetchResidualIncomeHistory } from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export function useResidualIncomeHistory(symbol: string): {
  loading:  boolean;
  error?:   string;
  history?: ResidualIncomeHistory;
  reload:   () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<ResidualIncomeHistory, Error>({
    queryKey:  QK.residualIncomeHistory(currentSymbol),
    queryFn:   () => fetchResidualIncomeHistory(currentSymbol),
    enabled:   !!currentSymbol,
    staleTime: STALE.HISTORY,
    gcTime:    GC.HISTORY,
    retry:     0,
  });

  const reload = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: QK.residualIncomeHistory(currentSymbol),
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