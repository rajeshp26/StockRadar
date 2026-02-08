// src/features/analysis/hooks/usePrice.ts
import { useEffect, useState } from "react";
import { fetchCurrentPrice } from "../services/price.service";

export function usePrice(symbol: string) {
  const [price, setPrice] = useState<number | null>(null);
  const [currency, setCurrency] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    if (!symbol) return;

    setLoading(true);
    fetchCurrentPrice(symbol)
      .then((data) => {
        if (!alive) return;
        if (data) {
          setPrice(data.price);
          setCurrency(data.currency ?? null);
        } else {
          setPrice(null);
          setCurrency(null);
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [symbol]);

  return { price, currency, loading };
}