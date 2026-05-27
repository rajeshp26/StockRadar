// web/src/features/analysis/utils/prefetch-valuations.ts
/**
 * Prefetch all five valuation methods simultaneously the moment the analysis
 * page mounts. By the time the user clicks any method tab, data is already
 * in the TanStack Query cache → instant render, zero spinner.
 *
 * How it works:
 *   - prefetchQuery fires a background GET request for each method.
 *   - If the cache is already warm (data within staleTime), it's a no-op.
 *   - On 404 (never computed), the cache is populated with { notComputed: true }
 *     so the component renders a "Run Computation" CTA immediately.
 *   - All 5 requests are fired in parallel — total latency = slowest individual
 *     GET (~50–150ms), not sum of all five.
 *
 * Usage in page.tsx:
 *   const queryClient = useQueryClient();
 *   useEffect(() => {
 *     prefetchAllValuations(upperSymbol, queryClient);
 *   }, [upperSymbol, queryClient]);
 */
import type { QueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { rule1QueryFn } from "@/features/analysis/hooks/useAnalysis";
import { dcfQueryFn } from "@/features/analysis/hooks/useDcfAnalysis";
import { riskQueryFn } from "@/features/analysis/hooks/useRiskAssessment";
import {
  fetchDdmCached,
  fetchOwnerEarningsCached,
  fetchResidualIncomeCached,
} from "@/features/analysis/services/analysis.service";
import type { DdmVariant } from "@/features/analysis/types/analysis.types";

const PREFETCH_OPTIONS = {
  staleTime: STALE.VALUATION,
  gcTime: GC.VALUATION,
} as const;

export function prefetchAllValuations(
  symbol: string,
  queryClient: QueryClient,
): void {
  if (!symbol) return;
  const upper = symbol.toUpperCase();

  // ── Rule #1 ────────────────────────────────────────────────────────────────
  queryClient.prefetchQuery({
    queryKey: QK.rule1(upper),
    queryFn: () => rule1QueryFn(upper),
    ...PREFETCH_OPTIONS,
  });

  // ── DCF ────────────────────────────────────────────────────────────────────
  queryClient.prefetchQuery({
    queryKey: QK.dcf(upper),
    queryFn: () => dcfQueryFn(upper),
    ...PREFETCH_OPTIONS,
  });

  // ── DDM (Gordon — default variant shown on tab) ────────────────────────────
  const ddmVariant: DdmVariant = "gordon";
  queryClient.prefetchQuery({
    queryKey: QK.ddm(upper, ddmVariant),
    queryFn: async () => {
      const outcome = await fetchDdmCached(upper, ddmVariant);
      if (outcome.status === "not_computed") return { notComputed: true };
      if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
      throw new Error(outcome.message);
    },
    ...PREFETCH_OPTIONS,
  });

  // ── Owner Earnings ─────────────────────────────────────────────────────────
  queryClient.prefetchQuery({
    queryKey: QK.ownerEarnings(upper),
    queryFn: async () => {
      const outcome = await fetchOwnerEarningsCached(upper);
      if (outcome.status === "not_computed") return { notComputed: true };
      if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
      throw new Error(outcome.message);
    },
    ...PREFETCH_OPTIONS,
  });

  // ── Residual Income ────────────────────────────────────────────────────────
  queryClient.prefetchQuery({
    queryKey: QK.residualIncome(upper),
    queryFn: async () => {
      const outcome = await fetchResidualIncomeCached(upper);
      if (outcome.status === "not_computed") return { notComputed: true };
      if (outcome.status === "ok") return { ...outcome.payload, notComputed: false };
      throw new Error(outcome.message);
    },
    ...PREFETCH_OPTIONS,
  });
  queryClient.prefetchQuery({
    queryKey: QK.magicFormula(symbol),
    queryFn: () => magicFormulaQueryFn(symbol),
    staleTime: STALE.VALUATION,
  });
  queryClient.prefetchQuery({
    queryKey: QK.canslim(symbol),
    queryFn: () => canslimQueryFn(symbol),
    staleTime: STALE.VALUATION,
  });
  queryClient.prefetchQuery({
    queryKey: QK.riskAssessment(upper),
    queryFn: () => riskQueryFn(upper),
    staleTime: STALE.VALUATION,
    gcTime: GC.VALUATION,
  });
}