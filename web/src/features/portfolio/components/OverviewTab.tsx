"use client";

import { TrendingUp, TrendingDown, DollarSign, Wallet, Banknote, BarChart3 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { usePortfolioOverview, usePortfolioAllocation } from "../hooks/usePortfolio";
import { LazyPerformanceChart } from "./LazyPerformanceChart";
import { AllocationOverviewCard } from "./AllocationOverviewCard";
import { formatCurrency } from "@/lib/currency";
import type { AllocationSegment, TypeAllocationSegment } from "../types/portfolio.types";

interface OverviewTabProps {
  accountIds?: number[];
}

function formatSignedCurrency(value: number | null | undefined): string {
  if (value == null) return "—";
  const text = formatCurrency(Math.abs(value));
  return value >= 0 ? `+${text}` : `-${text}`;
}

function formatSignedPct(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

interface KpiCard {
  label: string;
  value: string;
  subValue?: string;
  icon: LucideIcon;
  valueClass: string;
  subValueClass?: string;
}

function renderKpiCard(card: KpiCard) {
  const Icon = card.icon;
  return (
    <div key={card.label} className="glass-panel rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[10px] font-black uppercase tracking-widest text-white/40">
          {card.label}
        </p>
        <span className="p-1.5 rounded-lg bg-white/[0.03]">
          <Icon className="h-3.5 w-3.5 text-white/40" />
        </span>
      </div>
      <p className={`text-xl font-black ${card.valueClass}`}>{card.value}</p>
      {card.subValue != null && (
        <p className={`mt-1 text-xs font-bold ${card.subValueClass ?? "text-white/40"}`}>
          {card.subValue}
        </p>
      )}
    </div>
  );
}

export function OverviewTab({ accountIds }: OverviewTabProps) {
  const overviewIds = accountIds?.length === 1 ? accountIds : undefined;
  const { data: overview, isLoading: overviewLoading } = usePortfolioOverview(overviewIds);
  const { data: allocation, isLoading: allocationLoading } = usePortfolioAllocation(
    "sector",
    accountIds
  );

  const segments: AllocationSegment[] = allocation?.segments ?? [];
  const types: TypeAllocationSegment[] = allocation?.types ?? [];
  const hasAllocationData = segments.length > 0 || types.length > 0;

  if (overviewLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-[320px] rounded-2xl" />
      </div>
    );
  }

  if (
    !overview ||
    (typeof overview.total_value !== "number" && typeof overview.net_worth !== "number")
  ) {
    return (
      <div className="glass-panel rounded-lg p-8 text-center">
        <p className="text-white/40 text-sm">No portfolio data available.</p>
      </div>
    );
  }

  const ccy = overview.value_currency;
  const totalValue = overview.total_value ?? overview.net_worth;
  const cashBalance = overview.cash_balance ?? 0;
  const invested = overview.total_cost_basis ?? 0;
  const lifeDividends = overview.total_dividends ?? overview.ytd_dividends ?? 0;
  const gainPositive = (overview.total_gain_loss ?? 0) >= 0;
  const pctPositive = (overview.total_gain_loss_pct ?? 0) >= 0;

  const cards: KpiCard[] = [
    {
      label: "Amount Invested",
      value: formatCurrency(invested, ccy),
      subValue: `${overview.accounts_count ?? 0} ${(overview.accounts_count ?? 0) === 1 ? "account" : "accounts"}`,
      icon: BarChart3,
      valueClass: "text-white",
      subValueClass: "text-white/40",
    },
    {
      label: "Amount in Cash",
      value: formatCurrency(cashBalance, ccy),
      icon: Wallet,
      valueClass: "text-white",
    },
    {
      label: "Total Dividends",
      value: formatCurrency(lifeDividends, ccy),
      subValue: "Lifetime",
      icon: Banknote,
      valueClass: "text-white",
      subValueClass: "text-white/40",
    },
    {
      label: "Total Gain/Loss",
      value: formatSignedCurrency(overview.total_gain_loss),
      subValue: formatSignedPct(overview.total_gain_loss_pct),
      icon: gainPositive ? TrendingUp : TrendingDown,
      valueClass:
        overview.total_gain_loss == null
          ? "text-white/60"
          : gainPositive
            ? "text-green-400"
            : "text-red-400",
      subValueClass:
        overview.total_gain_loss_pct == null
          ? "text-white/40"
          : pctPositive
            ? "text-green-400/80"
            : "text-red-400/80",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="glass-panel rounded-lg p-5">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[10px] font-black uppercase tracking-widest text-white/40">
            Total Value
          </p>
          <span className="p-2 rounded-lg bg-white/[0.03]">
            <DollarSign className="h-4 w-4 text-white/40" />
          </span>
        </div>
        <p className="text-3xl font-black text-white">{formatCurrency(totalValue, ccy)}</p>
        <p className="mt-1 text-xs font-bold text-white/40">
          Holdings + cash across {overview.accounts_count ?? 0} account
          {(overview.accounts_count ?? 0) === 1 ? "" : "s"}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map(renderKpiCard)}
      </div>

      {/* Performance */}
      <LazyPerformanceChart accountIds={accountIds} />

      {/* Allocation */}
      {allocationLoading ? (
        <Skeleton className="h-[320px] rounded-2xl" />
      ) : !hasAllocationData ? (
        <div className="glass-panel rounded-lg p-8 text-center">
          <p className="text-white/40 text-sm">No allocation data available</p>
        </div>
      ) : (
        <AllocationOverviewCard
          types={types}
          segments={segments}
          totalValue={allocation?.total_value ?? 0}
          currency={ccy}
        />
      )}

      {/* Account Breakdown */}
      {overview.account_breakdown.length > 0 && (
        <div className="glass-panel rounded-lg p-6 space-y-4">
          <h3 className="text-xs font-black uppercase tracking-widest text-white/40">
            Account Breakdown
          </h3>
          <div className="space-y-3">
            {overview.account_breakdown.map((acct) => (
              <div
                key={acct.account_id}
                className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-white/5 transition-colors"
              >
                <div className="min-w-0">
                  <p className="text-sm font-bold text-white truncate">{acct.account_name}</p>
                  {acct.account_type && (
                    <p className="text-[10px] text-white/30">
                      {acct.account_type}
                      {acct.brokerage_name ? ` · ${acct.brokerage_name}` : ""}
                    </p>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-sm text-white/90">
                    {formatCurrency(acct.total_value, acct.value_currency || ccy)}
                  </p>
                  <p className="text-[10px] text-white/30">{acct.holdings_count} positions</p>
                  {acct.cash_balance != null && (
                    <p className="text-[10px] text-white/30">
                      Cash {formatCurrency(acct.cash_balance, acct.value_currency || ccy)}
                    </p>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <p className={acct.gain_loss >= 0 ? "text-green-400" : "text-red-400"}>
                    {formatSignedCurrency(acct.gain_loss)}
                  </p>
                  <p
                    className={`text-[10px] ${acct.gain_loss_pct >= 0 ? "text-green-400/70" : "text-red-400/70"}`}
                  >
                    {formatSignedPct(acct.gain_loss_pct)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
