// web/src/features/analysis/hooks/useMurphyAnalysis.ts
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMurphyTechnical } from "../services/analysis.service";
import type { MurphyAnalysisResponse } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { GC } from "@/lib/query-client";

// Murphy is stateless on the backend — always computed fresh from live price
// data. Stale time is 15 minutes (data changes intraday, not per-second).
const MURPHY_STALE_MS = 15 * 60 * 1000;

export function useMurphyAnalysis(symbol: string) {
    const upper = (symbol ?? "").toUpperCase();
    const queryClient = useQueryClient();

    const { data, isPending, error } = useQuery<MurphyAnalysisResponse, Error>({
        queryKey: QK.murphyTechnical(upper),
        queryFn: () => fetchMurphyTechnical(upper),
        enabled: !!upper,
        staleTime: MURPHY_STALE_MS,
        gcTime: GC.VALUATION,
        retry: 1,
    });

    const refresh = useCallback(async (): Promise<void> => {
        if (!upper) return;
        await queryClient.invalidateQueries({
            queryKey: QK.murphyTechnical(upper),
        });
    }, [upper, queryClient]);

    return {
        data: data ?? null,
        loading: isPending,
        error: error?.message ?? null,
        refresh,
    };
}