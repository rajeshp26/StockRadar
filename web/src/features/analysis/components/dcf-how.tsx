import { useDcfAnalysis } from "../hooks/useDcfAnalysis";
import { SectionHeader, fmtPct } from "./shared-ui";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-white/5 last:border-0">
      <span className="text-xs font-black uppercase tracking-widest text-white/30">{label}</span>
      <span className="text-xs font-bold text-white/70 text-right">{value}</span>
    </div>
  );
}

export function DcfHow({ symbol }: { symbol: string }) {
  const { data, loading } = useDcfAnalysis(symbol);

  if (loading || !data) return null;

  const v = data.valuation;

  return (
    <div className="glass-panel p-8">
      <SectionHeader
        title="How This DCF Was Calculated"
        subtitle="All assumptions resolved by the backend — no frontend calculations"
      />

      <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
        <Row label="Forecast Horizon"        value={`${v.forecastYears} years`} />
        <Row
          label="Free Cash Flow Forecast"
          value={v.forecastFcf.length > 0 ? `${v.forecastFcf.length} years projected` : "Not available"}
        />
        <Row label="Discount Rate (WACC)"    value={`${(v.waccUsed * 100).toFixed(2)}%`} />
        <Row label="Terminal Value Method"   value={v.terminalMethod} />
        {v.terminalValue != null && (
          <Row label="Terminal Value"        value={v.terminalValue.toLocaleString()} />
        )}
      </div>

      <p className="mt-4 text-[10px] text-white/20 leading-relaxed">
        All assumptions are resolved by the backend using reported financials, method defaults,
        and company overrides. No frontend calculations are performed.
      </p>
    </div>
  );
}