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
import { TimePeriodSelector } from '@/features/portfolio/components/TimePeriodSelector';
import { BenchmarkSelector } from '@/components/ui/benchmark-selector';
import { Metric } from '@/features/analysis/components/shared-ui';
import { SectionHeader } from '@/features/analysis/components/shared-ui';
import { Skeleton } from '@/components/ui/skeleton';
import { BENCHMARK_COLORS, FALLBACK_COLORS } from '@/lib/colors';
import { TrendingUp, TrendingDown, DollarSign, Wallet, Receipt, PiggyBank } from 'lucide-react';
import type { TimePeriod, HoldingPerformanceResponse, BenchmarkCompareResponse, HoldingTransaction, HoldingAccountBreakdown } from '@/features/portfolio/types/portfolio.types';
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
      {/* Summary Cards (P-01, P-07) */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricItem
          label="Total Value"
          value={perf.snapshots.length > 0
            ? `$${perf.snapshots[perf.snapshots.length - 1].position_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '—'}
          icon={DollarSign}
          color="text-white"
          subtitle={perf.snapshots.length > 0 && perf.snapshots[perf.snapshots.length - 1].shares_held
            ? `${perf.snapshots[perf.snapshots.length - 1].shares_held} shares`
            : undefined}
        />
        <MetricItem
          label="Total Invested"
          value={perf.snapshots.length > 0
            ? `$${perf.snapshots[perf.snapshots.length - 1].cumulative_invested.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '—'}
          icon={PiggyBank}
          color="text-white"
        />
        <MetricItem
          label="Gain/Loss ($)"
          value={perf.total_return != null
            ? `${perf.total_return >= 0 ? '+' : ''}$${perf.total_return.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '—'}
          icon={perf.total_return != null && perf.total_return >= 0 ? TrendingUp : TrendingDown}
          color={perf.total_return != null ? (perf.total_return >= 0 ? 'text-green-400' : 'text-red-400') : 'text-white/60'}
        />
        <MetricItem
          label="Gain/Loss (%)"
          value={perf.total_return_pct != null
            ? `${perf.total_return_pct >= 0 ? '+' : ''}${perf.total_return_pct.toFixed(2)}%`
            : '—'}
          icon={perf.total_return_pct != null && perf.total_return_pct >= 0 ? TrendingUp : TrendingDown}
          color={perf.total_return_pct != null ? (perf.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400') : 'text-white/60'}
        />
        <MetricItem
          label="Dividends"
          value={perf.total_dividends != null
            ? `$${perf.total_dividends.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
            : '—'}
          icon={Wallet}
          color="text-white"
        />
      </div>

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

function MetricItem({
  label,
  value,
  icon: Icon,
  color,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color: string;
  subtitle?: string;
}) {
  return (
    <div className="glass-panel rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-white/40 font-medium uppercase tracking-wider">{label}</p>
        <Icon className={`h-4 w-4 ${color}`} />
      </div>
      <p className={`text-xl font-bold mt-1 ${color}`}>{value}</p>
      {subtitle && (
        <p className="text-xs text-white/30 mt-0.5">{subtitle}</p>
      )}
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
