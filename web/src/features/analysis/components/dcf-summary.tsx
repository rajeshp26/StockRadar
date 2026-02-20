import { useDcfAnalysis } from "../hooks/useDcfAnalysis";
import { SectionHeader, fmtPct } from "./shared-ui";

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-white/5 last:border-0">
      <span className="text-xs font-black uppercase tracking-widest text-white/30">{label}</span>
      <span className="text-sm font-black text-white tabular-nums">{value}</span>
    </div>
  );
}

export function DcfSummary({ symbol }: { symbol: string }) {
  const { data, loading } = useDcfAnalysis(symbol);

  if (loading || !data) return null;

  const v = data.valuation;

  return (
    <div className="glass-panel p-8">
      <SectionHeader title="DCF Summary" />
      <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
        <StatRow
          label="Intrinsic Value / Share"
          value={v.intrinsicValuePerShare != null ? `$${v.intrinsicValuePerShare.toFixed(2)}` : "—"}
        />
        <StatRow label="Terminal Method" value={v.terminalMethod} />
        <StatRow label="WACC"            value={`${(v.waccUsed * 100).toFixed(2)}%`} />
        <StatRow
          label="Upside / Downside"
          value={v.upsideDownsidePct != null ? `${(v.upsideDownsidePct * 100).toFixed(1)}%` : "—"}
        />
      </div>
    </div>
  );
}