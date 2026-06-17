import { cn } from "@/lib/utils";
import { getValuationOverview, type ValuationOverviewData } from "@/lib/data/stocks";
import { TrendingUp, TrendingDown, CheckCircle2, Clock, AlertCircle, ChevronRight } from "lucide-react";

const METHOD_LABEL: Record<string, string> = {
  rule1:          "Rule #1 (Phil Town)",
  dcf:            "Discounted Cash Flow",
  ddm_gordon:     "Dividend Discount Model",
  owner_earnings: "Owner Earnings",
  residual_income: "Residual Income",
};

const METHOD_DESC: Record<string, string> = {
  rule1:          "Earnings growth & multiple based intrinsic value",
  dcf:            "Cash-flow based intrinsic value",
  ddm_gordon:     "Dividend yield & growth based valuation",
  owner_earnings: "Buffett owner earnings valuation",
  residual_income: "Economic profit based valuation",
};

function fmtCurrency(value: number | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function fmtUpside(value: number | null): string {
  if (value == null) return "—";
  const pct = value;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function StatusBadge({ status }: { status: string }) {
  if (status === "not_computed") {
    return (
      <span className="flex items-center gap-1 text-amber-400/70 text-[10px] font-black uppercase tracking-widest">
        <Clock className="h-3 w-3" />
        Not Run
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="flex items-center gap-1 text-rose-400/70 text-[10px] font-black uppercase tracking-widest">
        <AlertCircle className="h-3 w-3" />
        Error
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-black uppercase tracking-widest">
      <CheckCircle2 className="h-3 w-3" />
      Computed
    </span>
  );
}

function UpsideChip({ value }: { value: number | null }) {
  if (value == null) {
    return <span className="text-lg font-black text-white/20">—</span>;
  }
  const isPos = value >= 0;
  const Icon = isPos ? TrendingUp : TrendingDown;
  return (
    <span className={cn("flex items-center gap-1 text-lg font-black", isPos ? "text-emerald-400" : "text-rose-400")}>
      <Icon className="h-4 w-4" />
      {fmtUpside(value)}
    </span>
  );
}

function ScorePill({ score, category }: { score: number | null; category: string | null }) {
  if (score == null) return null;
  const colour =
    category === "Good" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" :
    category === "Caution" ? "bg-amber-500/15 text-amber-400 border-amber-500/25" :
    category === "Poor" ? "bg-rose-500/15 text-rose-400 border-rose-500/25" :
    "bg-white/5 text-white/40 border-white/10";
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-black uppercase tracking-wider", colour)}>
      {score}/100
    </span>
  );
}

function MethodRow({ method }: { method: ValuationOverviewData["methods"][number] }) {
  const isComputed = method.status === "computed";
  const label = METHOD_LABEL[method.method] ?? method.method;
  const desc = METHOD_DESC[method.method];
  return (
    <div className={cn("w-full text-left glass-card rounded-xl px-5 py-4 flex items-center gap-4 transition-all duration-200", !isComputed && "opacity-70")}>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-black text-white tracking-tight">{label}</p>
        {desc && <p className="text-xs text-white/45 truncate mt-0.5">{desc}</p>}
        {isComputed && method.lastComputedAt && (
          <p className="text-xs text-white/50 mt-0.5">Last run: {fmtDate(method.lastComputedAt)}</p>
        )}
      </div>
      <div className="text-right flex-shrink-0 w-24">
        {isComputed ? (
          <p className="text-sm font-black text-white">{fmtCurrency(method.intrinsicValue)}</p>
        ) : (
          <p className="text-sm font-black text-white/20">—</p>
        )}
        <p className="text-xs text-white/45 mt-0.5">Intrinsic</p>
      </div>
      <div className="text-right flex-shrink-0 w-20">
        <UpsideChip value={isComputed ? method.upsideDownside : null} />
        <p className="text-xs text-white/45 mt-0.5">vs Price</p>
      </div>
      <div className="text-right flex-shrink-0 w-28 space-y-1">
        {isComputed ? (
          <ScorePill score={method.score} category={method.category} />
        ) : (
          <StatusBadge status={method.status} />
        )}
        {isComputed && (
          <div className="flex justify-end">
            <StatusBadge status={method.status} />
          </div>
        )}
      </div>
      <ChevronRight className="h-3.5 w-3.5 text-white/15 flex-shrink-0" />
    </div>
  );
}

export async function ValuationOverviewRSC({ symbol }: { symbol: string }) {
  const data = await getValuationOverview(symbol);
  if (!data || data.methods.length === 0) {
    return (
      <div className="glass-panel p-8 text-center">
        <p className="text-sm text-white/40">No valuation data available for {symbol}.</p>
      </div>
    );
  }
  return (
    <div className="glass-panel p-8 space-y-6 animate-fade-up">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
          <TrendingUp className="h-4 w-4 text-indigo-400" />
        </div>
        <div>
          <h3 className="text-base font-black text-white tracking-tight">Valuation Overview</h3>
          <p className="text-[11px] text-white/35 mt-0.5">Compare intrinsic value estimates across methodologies</p>
        </div>
      </div>
      <div className="glass-divider" />
      <div className="space-y-2">
        {data.methods.map((m) => (
          <MethodRow key={m.method} method={m} />
        ))}
      </div>
      <p className="text-xs text-white/25 leading-relaxed border-t border-white/5 pt-4">
        Values refresh automatically when individual methods are recomputed.
      </p>
    </div>
  );
}
