import { useCallback, useEffect, useState } from "react";
import { fetchDcfValuation } from "../services/analysis.service";
import type { DcfResponse } from "../types/analysis.types";

export function useDcfAnalysis(symbol: string) {
  const [data, setData] = useState<DcfResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (force = false) => {
      try {
        setLoading(true);
        const resp = await fetchDcfValuation(symbol, { force });
        setData(resp);
        setError(null);
      } catch (e: any) {
        setError(e?.message ?? "Failed to load DCF valuation");
      } finally {
        setLoading(false);
      }
    },
    [symbol]
  );

  useEffect(() => {
    load(false);
  }, [load]);

  return {
    data,
    loading,
    error,
    recompute: () => load(true),
  };
}