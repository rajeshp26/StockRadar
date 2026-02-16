import { useCallback, useEffect, useState } from "react";
import { fetchDcfHistory } from "../services/analysis.service";
import type { DcfHistory } from "../types/analysis.types";

/**
 * DCF History hook
 * - Must NEVER break the Analysis page.
 * - If endpoint fails, return empty history.
 */
export function useDcfHistory(symbol: string) {
  const [history, setHistory] = useState<DcfHistory>({ symbol: symbol.toUpperCase(), items: [] });
  const [loadingHistory, setLoadingHistory] = useState(true);

  const load = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const resp = await fetchDcfHistory(symbol);
      // Defensive validation
      if (resp && typeof resp === "object" && Array.isArray(resp.items)) {
        setHistory({ symbol: (resp.symbol || symbol).toUpperCase(), items: resp.items });
      } else {
        setHistory({ symbol: symbol.toUpperCase(), items: [] });
      }
    } catch {
      setHistory({ symbol: symbol.toUpperCase(), items: [] });
    } finally {
      setLoadingHistory(false);
    }
  }, [symbol]);

  useEffect(() => {
    void load();
  }, [load]);

  return { history, loadingHistory, reloadHistory: load };
}