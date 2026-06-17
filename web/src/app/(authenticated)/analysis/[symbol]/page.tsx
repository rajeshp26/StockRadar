import { Suspense } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { PriceHeaderRSC } from "@/components/analysis/price-header-rsc";
import { ValuationOverviewRSC } from "@/components/analysis/valuation-overview-rsc";
import { ClientTabs } from "@/components/analysis/client-tabs";
import { AIChatBot } from "@/components/chat/ai-chat-bot";
import { Loader2, ArrowLeft } from "lucide-react";

function PriceSkeleton() {
  return (
    <div className="sticky top-14 z-20">
      <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
        <div className="relative flex flex-col gap-4 md:flex-row md:items-center">
          <div className="flex items-center gap-4">
            <div className="glass-btn flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0">
              <ArrowLeft className="h-4 w-4 text-white/60" />
            </div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-indigo-500/20 border border-indigo-500/30 text-sm font-black text-indigo-300 animate-pulse" />
              <div className="h-7 w-28 rounded-lg bg-white/5 animate-pulse" />
            </div>
          </div>
          <div className="flex items-baseline gap-3 md:ml-auto">
            <div className="h-7 w-24 rounded-lg bg-white/5 animate-pulse" />
          </div>
        </div>
      </div>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="glass-panel p-8 space-y-6 animate-fade-up">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
          <Loader2 className="h-4 w-4 text-indigo-400 animate-spin" />
        </div>
        <div>
          <div className="h-5 w-40 rounded-lg bg-white/5 animate-pulse" />
          <div className="h-3 w-64 rounded-lg bg-white/5 animate-pulse mt-1" />
        </div>
      </div>
      <div className="glass-divider" />
      <div className="space-y-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glass-card rounded-xl px-5 py-4 flex items-center gap-4">
            <div className="flex-1">
              <div className="h-4 w-24 rounded bg-white/5 animate-pulse" />
              <div className="h-3 w-32 rounded bg-white/5 animate-pulse mt-1" />
            </div>
            <div className="w-24">
              <div className="h-4 w-16 rounded bg-white/5 animate-pulse ml-auto" />
            </div>
            <div className="w-20">
              <div className="h-4 w-12 rounded bg-white/5 animate-pulse ml-auto" />
            </div>
            <div className="w-28">
              <div className="h-4 w-16 rounded bg-white/5 animate-pulse ml-auto" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PriceErrorFallback() {
  return (
    <div className="sticky top-14 z-20">
      <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
        <div className="relative flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/5 border border-white/10 text-sm font-black text-white/30 uppercase">
              ?
            </div>
            <p className="text-sm text-white/40">Price data temporarily unavailable.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function OverviewErrorFallback() {
  return (
    <div className="glass-panel p-8 text-center space-y-3">
      <p className="text-sm text-rose-400/80 font-bold">Failed to load valuation overview.</p>
      <p className="text-xs text-white/35">Please try refreshing the page.</p>
    </div>
  );
}

export default async function AnalysisPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: rawSymbol } = await params;
  const symbol = rawSymbol.toUpperCase();

  return (
    <div className="space-y-6 animate-fade-up">
      <ErrorBoundary fallback={<PriceErrorFallback />}>
        <Suspense fallback={<PriceSkeleton />}>
          <PriceHeaderRSC symbol={symbol} />
        </Suspense>
      </ErrorBoundary>

      <ClientTabs
        symbol={symbol}
        overviewChildren={
          <ErrorBoundary fallback={<OverviewErrorFallback />}>
            <Suspense fallback={<OverviewSkeleton />}>
              <ValuationOverviewRSC symbol={symbol} />
            </Suspense>
          </ErrorBoundary>
        }
      />

      <AIChatBot symbol={symbol} />
    </div>
  );
}
