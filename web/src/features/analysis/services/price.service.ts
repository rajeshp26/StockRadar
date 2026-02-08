// src/features/analysis/services/price.service.ts

/**
 * Fetch the current price for a symbol via the proxy.
 * This is intentionally non-throwing to avoid surfacing errors in the UI.
 * Return `null` if unavailable.
 */
export async function fetchCurrentPrice(
    symbol: string
  ): Promise<{ price: number; currency?: string } | null> {
    if (!symbol) return null;
  
    try {
      const res = await fetch(
        `/api/proxy/prices/${encodeURIComponent(symbol)}`,
        {
          method: "GET",
          headers: {
            "content-type": "application/json",
          },
          // Let the proxy inject the Firebase token, etc.
          cache: "no-store",
        }
      );
  
      if (!res.ok) {
        // Non-blocking: silently return null for unavailable price
        return null;
      }
  
      const data = await res.json();
  
      // Expected minimal shape: { price: number, currency?: string }
      if (typeof data?.price === "number") {
        return { price: data.price, currency: data.currency };
      }
      return null;
    } catch {
      // Never throw from price fetch
      return null;
    }
  }