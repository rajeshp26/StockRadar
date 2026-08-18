import { cache } from "react";
import { cookies } from "next/headers";

const BACKEND_URL = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8001";

async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const jar = await cookies();
    const session = jar.get("__session")?.value;
    return session ? { Authorization: `Bearer ${session}` } : {};
  } catch {
    return {};
  }
}

export interface QuoteData {
  symbol: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  lastUpdated: string | null;
  currency?: string | null;
}

export const getStockQuote = cache(async (symbol: string): Promise<QuoteData | null> => {
  try {
    const auth = await getAuthHeaders();
    const res = await fetch(`${BACKEND_URL}/stocks/${symbol}/quote`, {
      headers: { ...auth, Accept: "application/json" },
      next: { revalidate: 10, tags: [`quote-${symbol}`] },
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
});
