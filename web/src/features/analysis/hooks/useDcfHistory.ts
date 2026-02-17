"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DcfHistory } from "../types/analysis.types";
import { fetchDcfHistory } from "../services/analysis.service";

export function useDcfHistory(symbol: string): {
  loading: boolean;
  error?: string;
  history?: DcfHistory;
  reload: () => Promise<void>;
} {
  const currentSymbol = (symbol ?? "").toUpperCase();
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<DcfHistory | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(undefined);

  const ranForSymbol = useRef<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!currentSymbol) return;

    setLoading(true);
    setError(undefined);

    try {
      const h = await fetchDcfHistory(currentSymbol);
      setHistory(h);
    } catch (e: any) {
      setError(e?.message || "Could not load DCF history.");
      setHistory({ symbol: currentSymbol, items: [] });
    } finally {
      setLoading(false);
    }
  }, [currentSymbol]);

  useEffect(() => {
    if (!currentSymbol) return;
    if (!ranForSymbol.current[currentSymbol]) {
      ranForSymbol.current[currentSymbol] = true;
      void load();
    }
  }, [currentSymbol, load]);

  const reload = useCallback(async () => {
    await load();
  }, [load]);

  return { loading, error, history, reload };
}