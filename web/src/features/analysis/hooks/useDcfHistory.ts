// web/src/features/analysis/hooks/useDcfHistory.ts
"use client";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { DcfHistory } from "../types/analysis.types";
import { fetchDcfHistory } from "../services/analysis.service";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export function useDcfHistory(symbol: string): {
  loading:  boolean;
  error?:   string;
  history?: DcfHistory;
  reload:   () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const queryClient   = useQueryClient();

  const { data, isPending, error, refetch } = useQuery<DcfHistory, Error>({
    queryKey:  QK.dcfHistory(currentSymbol),
    queryFn:   () => fetchDcfHistory(currentSymbol),
    enabled:   !!currentSymbol,
    staleTime: STALE.HISTORY,
    gcTime:    GC.HISTORY,
    retry:     0, // non-critical; fetchDcfHistory already returns empty list on failure
  });

  const reload = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: QK.dcfHistory(currentSymbol) });
    await refetch();
  }, [currentSymbol, queryClient, refetch]);

  return {
    loading: isPending,
    error:   error?.message,
    history: data,
    reload,
  };
}