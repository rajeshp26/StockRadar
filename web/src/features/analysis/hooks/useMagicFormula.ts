// web/src/features/analysis/hooks/useMagicFormula.ts
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
    fetchMagicFormulaCached,
    fetchMagicFormulaValuation,
} from "../services/analysis.service";
import type { MagicFormulaResponse } from "../types/analysis.types";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

export type MagicFormulaQueryData =
    | { notComputed: true }
    | (MagicFormulaResponse & { notComputed: false });

export async function magicFormulaQueryFn(
    symbol: string
): Promise<MagicFormulaQueryData> {
    const outcome = await fetchMagicFormulaCached(symbol);
    if (outcome.status === "not_computed") return { notComputed: true };
    if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
    throw new Error(outcome.message || "Failed to load Magic Formula analysis.");
}

export function useMagicFormula(symbol: string) {
    const upper = (symbol ?? "").toUpperCase();
    const queryClient = useQueryClient();

    const { data, isPending, error } = useQuery<MagicFormulaQueryData, Error>({
        queryKey: QK.magicFormula(upper),
        queryFn: () => magicFormulaQueryFn(upper),
        enabled: !!upper,
        staleTime: STALE.VALUATION,
        gcTime: GC.VALUATION,
        retry: 1,
    });

    const recompute = useCallback(async (): Promise<void> => {
        if (!upper) return;
        const fresh = await fetchMagicFormulaValuation(upper, { force: true });
        queryClient.setQueryData<MagicFormulaQueryData>(QK.magicFormula(upper), {
            ...fresh,
            notComputed: false,
        });
    }, [upper, queryClient]);

    const notComputed = data?.notComputed ?? false;
    const responseData = notComputed
        ? null
        : (data as MagicFormulaResponse & { notComputed: false }) ?? null;

    return {
        data: responseData,
        loading: isPending,
        error: error?.message ?? null,
        notComputed,
        recompute,
    };
}