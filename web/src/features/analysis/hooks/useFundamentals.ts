"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { fetchFundamentals } from "../services/analysis.service";
import type { FundamentalsResponse } from "../types/analysis.types";
import { useCallback } from "react";

export function useFundamentals(symbol: string, frequency?: string) {
  const upper = (symbol ?? "").toUpperCase();
  const freq = frequency ?? "quarterly";
  const queryClient = useQueryClient();

  const { data, isPending, error } = useQuery<FundamentalsResponse, Error>({
    queryKey: QK.fundamentals(upper, freq),
    queryFn: () => fetchFundamentals(upper, freq),
    enabled: !!upper,
    staleTime: STALE.VALUATION,
    gcTime: GC.VALUATION,
    placeholderData: (prev) => prev,
    retry: 1,
  });

  const refetch = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: QK.fundamentals(upper, freq) });
  }, [upper, freq, queryClient]);

  return {
    data: data ?? null,
    loading: isPending,
    error: error?.message ?? data?.error ?? null,
    refetch,
  };
}
