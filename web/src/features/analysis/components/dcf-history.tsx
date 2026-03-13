import { cn } from "@/lib/utils";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useDcfHistory } from "../hooks/useDcfHistory";
import { SectionHeader, fmtCurrency, fmtPct, fmtInt, fmtDateTime } from "./shared-ui";

function HistoryRow({ cells, isHeader }: { cells: React.ReactNode[]; isHeader?: boolean }) {
  return (
    <div className={cn(
      "grid gap-2 px-4 py-3 text-xs grid-cols-[1.8fr_1fr_1fr_0.7fr_0.6fr_0.8fr]",
      isHeader
        ? "glass-overline border-b border-white/5"
        : "border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors",
    )}>
      {cells.map((cell, i) => (
        <div key={i} className={isHeader ? "" : "text-white/70 font-medium tabular-nums"}>{cell}</div>
      ))}
    </div>
  );
}

export function DcfHistory({ symbol }: { symbol: string }) {
  const { history, loading, error } = useDcfHistory(symbol);
  const items = history?.items;

  if (loading) return null;

  return (
    <div className="glass-panel p-8">
      <SectionHeader title="DCF History" subtitle="Previous computation runs" />

      {error && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-rose-500/8 border border-rose-500/20 mb-4">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-white/50">Failed to load DCF history.</p>
        </div>
      )}

      {!items || items.length === 0 ? (
        <p className="text-sm text-white/30 italic">No prior DCF valuation runs available.</p>
      ) : (
        <div className="rounded-2xl overflow-hidden border border-white/8">
          <HistoryRow cells={["Date", "Intrinsic / Share", "WACC", "Terminal Method", "Score", "Category"]} isHeader />
          {items.map((h, idx) => (
            <HistoryRow
              key={idx}
              cells={[
                h.runAt ? new Date(h.runAt).toLocaleDateString() : "—",
                h.intrinsicValuePerShare != null ? `$${h.intrinsicValuePerShare.toFixed(2)}` : "—",
                h.waccUsed != null ? `${(h.waccUsed * 100).toFixed(2)}%` : "—",
                h.terminalMethod ?? "—",
                h.score ?? "—",
                h.category ?? "—",
              ]}
            />
          ))}
        </div>
      )}
    </div>
  );
}