// web/src/features/analysis/utils/prefetch-valuations.ts
/**
 * Prefetch the canonical valuation summary the moment the analysis page
 * mounts. One GET (/analysis/{symbol}/valuation-summary) covers all five
 * valuation methods — the 5 per-method GETs + /overview that used to fire
 * here are gone (§6.1). Method tabs that are NOT on the critical path are
 * prefetched lazily by usePredictiveTabPrefetch (idle callback) instead.
 *
 * Usage in page.tsx / client-tabs.tsx:
 *   const queryClient = useQueryClient();
 *   useEffect(() => {
 *     prefetchAllValuations(upperSymbol, queryClient);
 *   }, [upperSymbol, queryClient]);
 */
import type { QueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { fetchValuationSummary } from "@/features/analysis/services/analysis.service";

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

  queryClient.prefetchQuery({
    queryKey: QK.valuationSummary(upper),
    queryFn: () => fetchValuationSummary(upper),
    ...PREFETCH_OPTIONS,
  });
}
