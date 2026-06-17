import { getStockQuote } from "@/lib/data/stocks";
import { LivePriceHeader } from "./live-price-header";

export async function PriceHeaderRSC({ symbol }: { symbol: string }) {
  const quote = await getStockQuote(symbol);
  return (
    <LivePriceHeader
      symbol={symbol}
      initialPrice={quote?.price ?? null}
      initialChange={quote?.change ?? null}
      initialChangePercent={quote?.changePercent ?? null}
      initialLastUpdated={quote?.lastUpdated ?? null}
    />
  );
}
