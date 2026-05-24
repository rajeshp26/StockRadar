"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStockVsIndex, fetchBenchmarks } from "@/features/analysis/services/analysis.service";
import type { StockVsIndexResponse } from "../types/analysis.types";
import type { BenchmarkInfo } from "@/lib/types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export function useStockVsIndex(
    symbol: string,
    benchmarkSymbols: string[] = ["SPY"],
    years: number = 3
): {
    loading: boolean;
    error?: string;
    data?: StockVsIndexResponse;
} {
    const currentSymbol = (symbol ?? "").toUpperCase();
    const sortedBm = [...benchmarkSymbols].sort();

    const { data, isPending, error } = useQuery<StockVsIndexResponse, Error>({
        queryKey: QK.stockVsIndex(currentSymbol, sortedBm, years),
        queryFn: () => fetchStockVsIndex(currentSymbol, sortedBm, years),
        enabled: !!currentSymbol && sortedBm.length > 0,
        staleTime: STALE.VALUATION,
        gcTime: GC.VALUATION,
        retry: 1,
    });

    return {
        loading: isPending,
        error: error?.message,
        data,
    };
}

export function useAnalysisBenchmarks() {
    return useQuery<BenchmarkInfo[], Error>({
        queryKey: ["analysis", "benchmarks"] as const,
        queryFn: () => fetchBenchmarks(),
        staleTime: STALE.STATIC,
        gcTime: GC.STATIC,
        retry: 1,
    });
}