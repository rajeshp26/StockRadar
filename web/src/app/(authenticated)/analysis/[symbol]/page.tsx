"use client";

import { useParams } from "next/navigation";
import { LivePriceHeader } from "@/components/analysis/live-price-header";
import { ClientTabs } from "@/components/analysis/client-tabs";
import { AIChatBot } from "@/components/chat/ai-chat-bot";

export default function AnalysisPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = (params.symbol ?? "").toUpperCase();

  if (!symbol) return null;

  return (
    <div className="space-y-6 animate-fade-up">
      <LivePriceHeader
        symbol={symbol}
        initialPrice={null}
        initialChange={null}
        initialChangePercent={null}
        initialLastUpdated={null}
      />

      <ClientTabs symbol={symbol} />

      <AIChatBot symbol={symbol} />
    </div>
  );
}
