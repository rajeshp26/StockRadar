'use client';

import { useState } from 'react';
import {
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  Line,
  ComposedChart,
  BarChart,
  Bar,
  Legend,
} from 'recharts';
import { useHoldingPerformance, useHoldingDividends, useBenchmarks, useBenchmarkCompare, useHoldingTransactions, useHoldingAccounts, useHoldingBenchmarkCompare } from '@/features/portfolio/hooks/usePortfolio';
import { useLivePrice } from '@/features/analysis/hooks/useLivePrice';
import { TimePeriodSelector } from '@/features/portfolio/components/TimePeriodSelector';
import { BenchmarkSelector } from '@/components/ui/benchmark-selector';
import { Metric } from '@/features/analysis/components/shared-ui';
import { SectionHeader } from '@/features/analysis/components/shared-ui';
import { Skeleton } from '@/components/ui/skeleton';
import { BENCHMARK_COLORS, FALLBACK_COLORS } from '@/lib/colors';
import { TrendingUp, TrendingDown, DollarSign, Wallet, Receipt, PiggyBank, Calendar, Activity, ArrowUpRight, CalendarDays, BarChart3 } from 'lucide-react';
import type { TimePeriod, HoldingPerformanceResponse, BenchmarkCompareResponse, HoldingTransaction, HoldingAccountBreakdown, MonthlyReturnSummary, DrawdownInfo, DaysAboveCostBasis } from '@/features/portfolio/types/portfolio.types';
import { cn } from '@/lib/utils';

interface StockPerformancePanelProps {
  symbol: string;
}

export function StockPerformancePanel({ symbol }: StockPerformancePanelProps) {
  const [period, setPeriod] = useState<TimePeriod>('1Y');
  const [selectedBenchmarks, setSelectedBenchmarks] = useState<string[]>([]);

  const { data: perf, isLoading: perfLoading, isError: perfError } = useHoldingPerformance(symbol, period);
  const { data: dividends, isLoading: divLoading } = useHoldingDividends(symbol);
  const { data: benchmarks } = useBenchmarks();
  const { data: transactions, isLoading: txLoading } = useHoldingTransactions(symbol);
  const { data: accounts, isLoading: acctLoading } = useHoldingAccounts(symbol);
  const { data: compareData, isLoading: compareLoading, isError: compareError } = useHoldingBenchmarkCompare(symbol, period, selectedBenchmarks);

  if (perfError) {
    return (
      <div className="glass-panel rounded-lg p-8 text-center">
        <p className="text-white/40 text-sm">Unable to load performance data</p>
      </div>
    );
  }

  if (perfLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-8 w-full rounded-lg" />
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    );
  }

  if (!perf) {
    return (
      <div className="glass-panel rounded-lg p-8 text-center">
        <p className="text-white/40 text-sm">No performance data yet</p>
      </div>
    );
  }

  const showBenchmarks = selectedBenchmarks.length > 0;
  const chartData = buildPerformanceChartData(perf, compareData, selectedBenchmarks);
  const hasChartData = chartData.length > 1 && chartData.some((d) => (d.position_value as number) > 0);
  const firstNonZeroSnapshot = perf.snapshots.find((s) => s.position_value > 0);
  const hasPrePurchaseData = firstNonZeroSnapshot && chartData.some((d) => d.date < firstNonZeroSnapshot.date);

  return (
    <div className="space-y-6">
      {/* Performance Summary Card */}
      <PerformanceSummaryCard perf={perf} symbol={symbol} />

      {/* Performance Chart */}
      <div className="glass-panel p-6">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <SectionHeader title="Performance vs Cost Basis" subtitle="Position value over time" />
          <div className="flex items-center gap-3">
            <BenchmarkSelector
              benchmarks={benchmarks || []}
              selected={selectedBenchmarks}
              onToggle={(sym) =>
                setSelectedBenchmarks((prev) =>
                  prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]
                )
              }
            />
            <TimePeriodSelector value={period} onChange={setPeriod} />
          </div>
        </div>

        {showBenchmarks && compareLoading && (
          <div className="mb-2 text-xs text-white/30 italic">Loading benchmark data...</div>
        )}
        {showBenchmarks && compareError && (
          <div className="mb-2 text-xs text-red-400/60">Failed to load benchmark data</div>
        )}
        {hasPrePurchaseData && (
          <div className="mb-2 text-xs text-white/20 text-center py-1 border-t border-b border-white/5">
            No position held before {firstNonZeroSnapshot?.date}
          </div>
        )}
        <div className="h-[300px] md:h-[400px]">
          {hasChartData ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(val: string) => {
                    const d = new Date(val);
                    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                  }}
                />
                <YAxis
                  tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(val: number) =>
                    val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(0)
                  }
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const snap = perf.snapshots.find((s) => s.date === label);
                    return (
                      <div className="bg-[rgba(12,15,28,0.95)] border border-white/10 rounded-xl backdrop-blur-xl px-4 py-3 text-xs">
                        <p className="text-white/60 mb-1.5">{label}</p>
                        {payload.map((entry, idx) => (
                          <p key={idx} style={{ color: entry.color }} className="font-medium">
                            {entry.name}: {typeof entry.value === 'number' ? entry.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : entry.value}
                          </p>
                        ))}
                        {snap?.shares_held != null && snap.shares_held > 0 && (
                          <>
                            <p className="text-white/40 mt-1.5 border-t border-white/10 pt-1.5">
                              Shares Held: {snap.shares_held}
                            </p>
                            {snap.avg_cost_per_share != null && (
                              <p className="text-white/40">
                                Avg Cost/Share: ${snap.avg_cost_per_share.toFixed(2)}
                              </p>
                            )}
                          </>
                        )}
                      </div>
                    );
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="position_value"
                  stroke="#818cf8"
                  fill="#818cf8"
                  fillOpacity={0.15}
                  strokeWidth={2}
                  name="Position Value"
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="cost_basis"
                  stroke="#34d399"
                  strokeWidth={2}
                  strokeDasharray="4 2"
                  name="Cost Basis"
                  dot={false}
                />
                {selectedBenchmarks.map((sym, i) => (
                  <Line
                    key={sym}
                    type="monotone"
                    dataKey={sym}
                    stroke={BENCHMARK_COLORS[sym] || FALLBACK_COLORS[i % FALLBACK_COLORS.length]}
                    strokeWidth={2}
                    strokeDasharray="6 3"
                    name={sym}
                    dot={false}
                  />
                ))}
                <Legend
                  wrapperStyle={{
                    fontSize: 12,
                    color: 'rgba(255,255,255,0.5)',
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center">
              <p className="text-white/20 text-sm">
                {chartData.length <= 1
                  ? 'Need at least 2 data points to render a chart'
                  : 'All position values are zero'}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Dividend Bar Chart */}
      <div className="glass-panel p-6">
        <SectionHeader title="Dividend History" subtitle="Quarterly dividends received" />
        <div className="h-[250px] mt-4">
          {divLoading ? (
            <Skeleton className="h-full w-full rounded-lg" />
          ) : dividends && dividends.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dividends}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis
                  dataKey="label"
                  tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(val: number) =>
                    val >= 1000 ? `${(val / 1000).toFixed(1)}k` : val.toFixed(0)
                  }
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(12,15,28,0.95)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '12px',
                    backdropFilter: 'blur(20px)',
                  }}
                  labelStyle={{ color: 'rgba(255,255,255,0.6)', fontSize: 12 }}
                  itemStyle={{ fontSize: 13 }}
                />
                <Bar dataKey="total_amount" fill="#34d399" name="Dividends Received" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center">
              <p className="text-white/20 text-sm">No dividend data available</p>
            </div>
          )}
        </div>
      </div>

      {/* Transaction History (P-04) */}
      <div className="glass-panel p-6">
        <SectionHeader title="Transaction History" subtitle="All buys and sells for this position" />
        <div className="mt-4">
          {txLoading ? (
            <Skeleton className="h-24 w-full rounded-lg" />
          ) : transactions && transactions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/40 text-xs uppercase tracking-wider border-b border-white/5">
                    <th className="text-left py-2 pr-4">Date</th>
                    <th className="text-left py-2 pr-4">Type</th>
                    <th className="text-right py-2 pr-4">Qty</th>
                    <th className="text-right py-2 pr-4">Price</th>
                    <th className="text-right py-2 pr-4">Commission</th>
                    <th className="text-right py-2 pr-4">Net Cash</th>
                    <th className="text-left py-2 pr-4">Account</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx: HoldingTransaction) => (
                    <tr key={tx.transaction_id} className="border-b border-white/5 last:border-0">
                      <td className="py-2 pr-4 text-white/60 whitespace-nowrap">{tx.transaction_date}</td>
                      <td className={`py-2 pr-4 font-medium ${tx.activity_sub_type === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                        {tx.activity_sub_type}
                      </td>
                      <td className="py-2 pr-4 text-right text-white">{tx.quantity}</td>
                      <td className="py-2 pr-4 text-right text-white">${tx.unit_price.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-right text-white/60">${tx.commission.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-right text-white">${tx.net_cash_amount.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-white/40">{tx.account_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-white/20 text-sm text-center py-4">No transaction history available</p>
          )}
        </div>
      </div>

      {/* Account Breakdown (P-05) */}
      <div className="glass-panel p-6">
        <SectionHeader title="Holdings by Account" subtitle="Position details per account" />
        <div className="mt-4">
          {acctLoading ? (
            <Skeleton className="h-24 w-full rounded-lg" />
          ) : accounts && accounts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-white/40 text-xs uppercase tracking-wider border-b border-white/5">
                    <th className="text-left py-2 pr-4">Account</th>
                    <th className="text-left py-2 pr-4">Type</th>
                    <th className="text-right py-2 pr-4">Shares</th>
                    <th className="text-right py-2 pr-4">Cost</th>
                    <th className="text-right py-2 pr-4">Value</th>
                    <th className="text-right py-2 pr-4">G/L $</th>
                    <th className="text-right py-2 pr-4">G/L %</th>
                    <th className="text-right py-2 pr-4">Dividends</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((acct: HoldingAccountBreakdown) => (
                    <tr key={acct.account_id} className="border-b border-white/5 last:border-0">
                      <td className="py-2 pr-4 text-white whitespace-nowrap">{acct.account_name}</td>
                      <td className="py-2 pr-4 text-white/60">{acct.account_type}</td>
                      <td className="py-2 pr-4 text-right text-white">{acct.shares_held}</td>
                      <td className="py-2 pr-4 text-right text-white">${acct.total_cost.toFixed(2)}</td>
                      <td className="py-2 pr-4 text-right text-white">${acct.current_value.toFixed(2)}</td>
                      <td className={`py-2 pr-4 text-right font-medium ${acct.unrealized_gain_loss >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {acct.unrealized_gain_loss >= 0 ? '+' : ''}${acct.unrealized_gain_loss.toFixed(2)}
                      </td>
                      <td className={`py-2 pr-4 text-right font-medium ${acct.unrealized_gain_loss_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {acct.unrealized_gain_loss_pct >= 0 ? '+' : ''}{acct.unrealized_gain_loss_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 pr-4 text-right text-white">${acct.dividends_received.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-white/20 text-sm text-center py-4">No account breakdown available</p>
          )}
        </div>
      </div>
    </div>
  );
}

function PerformanceSummaryCard({
  perf,
  symbol,
}: {
  perf: HoldingPerformanceResponse;
  symbol: string;
}) {
  const { price: livePrice } = useLivePrice(symbol);
  const lastSnapshot = perf.snapshots[perf.snapshots.length - 1];
  const avgCost = lastSnapshot?.avg_cost_per_share;
  const showMonthlyMetrics = !['ALL', '5Y'].includes(perf.period?.toUpperCase() ?? '');
  const perfColor = perf.combined_return >= 0 ? 'text-green-400' : 'text-red-400';

  return (
    <div className="glass-panel rounded-lg p-5 space-y-4">
      {/* Header: Gain/Loss headline */}
      <div className="flex items-baseline justify-between">
        <div>
          <p className="text-xs text-white/40 font-medium uppercase tracking-wider">Gain / Loss</p>
          <p className={`text-2xl font-black tracking-tight ${perfColor}`}>
            {perf.combined_return >= 0 ? '+' : ''}$
            {Math.abs(perf.combined_return).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            <span className={`text-sm font-bold ml-1.5 ${perfColor}`}>
              {perf.total_return_pct >= 0 ? '+' : ''}{perf.total_return_pct.toFixed(2)}%
            </span>
          </p>
        </div>
        {lastSnapshot && (
          <div className="text-right">
            <p className="text-xs text-white/40 font-medium uppercase tracking-wider">Current Value</p>
            <p className="text-lg font-bold text-white">
              ${lastSnapshot.position_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        )}
      </div>

      {/* Row 1: Attribution — Price change + Dividends */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3.5 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <ArrowUpRight className="h-3 w-3" />
            Price Change
          </div>
          <p className={`text-sm font-bold ${perf.total_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {perf.total_return >= 0 ? '+' : ''}${Math.abs(perf.total_return).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            <span className="text-xs ml-1">({perf.total_return_pct >= 0 ? '+' : ''}{perf.total_return_pct.toFixed(2)}%)</span>
          </p>
        </div>
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3.5 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <Wallet className="h-3 w-3" />
            Dividends
          </div>
          <p className="text-sm font-bold text-green-400">
            +${perf.total_dividends.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            {perf.total_dividends_pct > 0 && (
              <span className="text-xs ml-1">({perf.total_dividends_pct.toFixed(2)}%)</span>
            )}
          </p>
        </div>
      </div>

      {/* Context line: Avg Cost → Last Price */}
      {avgCost != null && livePrice != null && (
        <div className="flex items-center justify-center gap-2 text-xs text-white/50 border-t border-white/[0.06] pt-3">
          <span>Avg Cost <span className="text-white font-medium">${avgCost.toFixed(2)}</span></span>
          <span className="text-white/20">→</span>
          <span>Last Price <span className="text-white font-medium">${livePrice.toFixed(2)}</span></span>
          <span className={`font-medium ${livePrice >= avgCost ? 'text-green-400' : 'text-red-400'}`}>
            {livePrice >= avgCost ? '+' : ''}{((livePrice - avgCost) / avgCost * 100).toFixed(2)}%
          </span>
        </div>
      )}

      {/* Row 2: Risk quadrants (4-col) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Best Month */}
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <TrendingUp className="h-3 w-3 text-green-400" />
            Best Month
          </div>
          {showMonthlyMetrics && perf.best_month ? (
            <>
              <p className="text-sm font-bold text-green-400">+{perf.best_month.return_pct.toFixed(2)}%</p>
              <p className="text-[10px] text-white/30">{perf.best_month.label}</p>
            </>
          ) : (
            <p className="text-sm text-white/30">—</p>
          )}
        </div>

        {/* Worst Month */}
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <TrendingDown className="h-3 w-3 text-red-400" />
            Worst Month
          </div>
          {showMonthlyMetrics && perf.worst_month ? (
            <>
              <p className="text-sm font-bold text-red-400">{perf.worst_month.return_pct.toFixed(2)}%</p>
              <p className="text-[10px] text-white/30">{perf.worst_month.label}</p>
            </>
          ) : (
            <p className="text-sm text-white/30">—</p>
          )}
        </div>

        {/* Max Drawdown */}
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <TrendingDown className="h-3 w-3 text-red-400" />
            Max Drawdown
          </div>
          {perf.max_drawdown ? (
            <>
              <p className="text-sm font-bold text-red-400">{perf.max_drawdown.dd_pct.toFixed(2)}%</p>
              <p className="text-[10px] text-white/30">{perf.max_drawdown.duration_days}d</p>
            </>
          ) : (
            <p className="text-sm text-white/30">—</p>
          )}
        </div>

        {/* Volatility (30d) */}
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <Activity className="h-3 w-3 text-indigo-400" />
            Volatility (30d)
          </div>
          <p className="text-sm font-bold text-indigo-400">
            {perf.volatility_30d > 0 ? `${perf.volatility_30d.toFixed(2)}%` : '—'}
          </p>
        </div>
      </div>

      {/* Row 3: Extended metrics (2-col) */}
      <div className="grid grid-cols-2 gap-3">
        {/* Days Above Cost Basis */}
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <CalendarDays className="h-3 w-3 text-white/50" />
            Days Above Cost Basis
          </div>
          {perf.days_above_cost_basis ? (
            <>
              <p className="text-sm font-bold text-white">
                {perf.days_above_cost_basis.days_above} / {perf.days_above_cost_basis.total_days} days
              </p>
              <p className="text-[10px] text-white/30">{perf.days_above_cost_basis.pct_above.toFixed(1)}% of time</p>
            </>
          ) : (
            <p className="text-sm text-white/30">—</p>
          )}
        </div>

        {/* Longest Drawdown */}
        <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
          <div className="flex items-center gap-1.5 text-xs text-white/40 font-medium mb-1">
            <BarChart3 className="h-3 w-3 text-red-400" />
            Longest Drawdown
          </div>
          {perf.longest_drawdown ? (
            <>
              <p className="text-sm font-bold text-red-400">{perf.longest_drawdown.dd_pct.toFixed(2)}%</p>
              <p className="text-[10px] text-white/30">
                {perf.longest_drawdown.is_ongoing ? '→ now · Ongoing' : `${perf.longest_drawdown.duration_days}d`}
              </p>
            </>
          ) : (
            <p className="text-sm text-white/30">—</p>
          )}
        </div>
      </div>
    </div>
  );
}

function buildPerformanceChartData(
  perf: HoldingPerformanceResponse,
  compareData: BenchmarkCompareResponse | undefined,
  selectedBenchmarks: string[],
): Record<string, unknown>[] {
  if (!perf.snapshots || perf.snapshots.length === 0) return [];

  if (!compareData || selectedBenchmarks.length === 0) {
    return perf.snapshots.map((s) => ({
      date: s.date,
      position_value: s.position_value,
      cost_basis: s.cost_basis,
    }));
  }

  const dateMap: Record<string, Record<string, unknown>> = {};
  for (const s of perf.snapshots) {
    dateMap[s.date] = {
      ...dateMap[s.date],
      date: s.date,
      position_value: s.position_value,
      cost_basis: s.cost_basis,
    };
  }
  if (compareData.benchmarks) {
    for (const bs of compareData.benchmarks) {
      for (const point of bs.data) {
        dateMap[point.date] = {
          ...dateMap[point.date],
          date: point.date,
          [bs.symbol]: point.value,
        };
      }
    }
  }

  const sortedDates = Object.keys(dateMap).sort();
  return sortedDates.map((date) => dateMap[date]!);
}
