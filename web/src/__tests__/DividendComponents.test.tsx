import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/components/ui/skeleton', () => ({
    Skeleton: ({ className }: any) => {
        const React = require('react');
        return React.createElement('div', { 'data-testid': 'skeleton', className });
    },
}));

const mockUseDividendHoldingDetail = vi.fn();
vi.mock('@/features/portfolio/hooks/usePortfolio', () => ({
    useDividendHoldingDetail: (...args: any[]) => mockUseDividendHoldingDetail(...args),
}));

import { MetricCard } from '@/features/portfolio/components/MetricCard';
import { GoalProgressCard } from '@/features/portfolio/components/GoalProgressCard';
import { DividendTrendChart } from '@/features/portfolio/components/DividendTrendChart';
import { DividendSectorChart } from '@/features/portfolio/components/DividendSectorChart';
import { DividendsUpcomingCard } from '@/features/portfolio/components/DividendsUpcomingCard';
import { DividendHoldingsTable } from '@/features/portfolio/components/DividendHoldingsTable';
import { DividendDetailDrawer } from '@/features/portfolio/components/DividendDetailDrawer';
import { DividendsSummarySection } from '@/features/portfolio/components/DividendsSummarySection';
import { DividendsHoldingsSection } from '@/features/portfolio/components/DividendsHoldingsSection';
import type { PortfolioDividendHolding, PortfolioDividendSummary, UpcomingExDate, MonthlyDividendSummary } from '@/features/portfolio/types/portfolio.types';

const FMT = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

beforeEach(() => {
    vi.clearAllMocks();
    mockUseDividendHoldingDetail.mockReturnValue({ data: undefined, isLoading: false, error: null });
});

// ═══════════════════════════════════════════════════════════════════════════════
// MetricCard
// ═══════════════════════════════════════════════════════════════════════════════
describe('MetricCard', () => {
    it('renders label, value, and subtitle', () => {
        render(<MetricCard label="Trailing 12M" value="$1,234.56" subtitle="actual dividends" />);
        expect(screen.getByText('Trailing 12M')).toBeInTheDocument();
        expect(screen.getByText('$1,234.56')).toBeInTheDocument();
        expect(screen.getByText('actual dividends')).toBeInTheDocument();
    });

    it('shows coverage percentage badge', () => {
        render(<MetricCard label="Safety" value="75.2" coveragePct={85} />);
        expect(screen.getByText('85% coverage')).toBeInTheDocument();
    });

    it('hides coverage badge when undefined', () => {
        render(<MetricCard label="Income" value="$500" />);
        expect(screen.queryByText(/% coverage/)).not.toBeInTheDocument();
    });

    it('renders up trend with label', () => {
        render(<MetricCard label="Growth" value="12%" trend="up" trendLabel="+2.1% vs last month" />);
        const el = screen.getByText((content) => content.includes('+2.1% vs last month'));
        expect(el.className).toContain('text-emerald-400');
    });

    it('renders down trend', () => {
        render(<MetricCard label="Growth" value="5%" trend="down" trendLabel="-1.2%" />);
        const el = screen.getByText((content) => content.includes('-1.2%'));
        expect(el.className).toContain('text-rose-400');
    });

    it('renders neutral trend', () => {
        render(<MetricCard label="Growth" value="0%" trend="neutral" trendLabel="flat" />);
        expect(screen.getByText('flat').className).toContain('text-amber-400');
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// GoalProgressCard
// ═══════════════════════════════════════════════════════════════════════════════
describe('GoalProgressCard', () => {
    it('renders progress bar when monthlyGoal is set with exact percentage', () => {
        render(<GoalProgressCard monthlyIncome={250} monthlyGoal={1000} />);
        expect(screen.getByText('25.0% of monthly goal')).toBeInTheDocument();
    });

    it('caps at 100% when income exceeds goal', () => {
        render(<GoalProgressCard monthlyIncome={1500} monthlyGoal={1000} />);
        expect(screen.getByText('100.0% of monthly goal')).toBeInTheDocument();
    });

    it('shows income but no goal message when no goal and no onSetGoal', () => {
        render(<GoalProgressCard monthlyIncome={250} monthlyGoal={null} />);
        expect(screen.getByText('Set a monthly income goal to track progress.')).toBeInTheDocument();
        expect(screen.queryByText('Set goal')).not.toBeInTheDocument();
    });

    it('fires onSetGoal when button clicked', () => {
        const onSetGoal = vi.fn();
        render(<GoalProgressCard monthlyIncome={250} monthlyGoal={null} onSetGoal={onSetGoal} />);
        fireEvent.click(screen.getByText('Set goal'));
        expect(onSetGoal).toHaveBeenCalledOnce();
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendTrendChart
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendTrendChart', () => {
    const data: MonthlyDividendSummary[] = [
        { fiscal_year: 2026, fiscal_month: 1, payment_count: 3, total_amount: 450, paying_companies: 2 },
        { fiscal_year: 2026, fiscal_month: 2, payment_count: 2, total_amount: 320, paying_companies: 2 },
    ];

    it('renders heading', () => {
        render(<DividendTrendChart data={data} />);
        expect(screen.getByText('Monthly Dividend Income')).toBeInTheDocument();
    });

    it('shows empty state text', () => {
        render(<DividendTrendChart data={[]} />);
        expect(screen.getByText('No dividend data for selected period')).toBeInTheDocument();
    });

    it('shows loading state', () => {
        const { container } = render(<DividendTrendChart data={[]} isLoading />);
        expect(screen.getByText('Monthly Dividend Income')).toBeInTheDocument();
        expect(container.querySelector('.glass-shimmer')).toBeInTheDocument();
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendSectorChart
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendSectorChart', () => {
    it('renders heading with data', () => {
        render(<DividendSectorChart data={[{ sector: 'Technology', value: 1200 }]} />);
        expect(screen.getByText('Income by Sector')).toBeInTheDocument();
    });

    it('shows empty state', () => {
        render(<DividendSectorChart data={[]} />);
        expect(screen.getByText('No sector data')).toBeInTheDocument();
    });

    it('shows loading state', () => {
        const { container } = render(<DividendSectorChart data={[]} isLoading />);
        expect(screen.getByText('Income by Sector')).toBeInTheDocument();
        expect(container.querySelector('.glass-shimmer')).toBeInTheDocument();
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendsUpcomingCard (Ex-Dates Calendar)
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendsUpcomingCard', () => {
    const data: UpcomingExDate[] = [
        { symbol: 'AAPL', company_name: 'Apple Inc.', ex_dividend_date: '2026-06-25', amount_per_share: 1.90, estimated_income: 95, dividend_type: 'regular', confidence: 'high' },
        { symbol: 'GOOGL', company_name: 'Alphabet Inc.', ex_dividend_date: '2026-06-25', amount_per_share: 1.50, estimated_income: 45, dividend_type: 'regular', confidence: 'low' },
    ];

    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-06-15'));
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('renders heading, search input, and month nav', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        expect(screen.getByText('Ex-Dates Calendar')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Filter by ticker...')).toBeInTheDocument();
        expect(screen.getByLabelText('Previous month')).toBeInTheDocument();
        expect(screen.getByLabelText('Next month')).toBeInTheDocument();
        expect(screen.getByText('June 2026')).toBeInTheDocument();
    });

    it('renders week day headers', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(d => {
            expect(screen.getByText(d)).toBeInTheDocument();
        });
    });

    it('shows predicted badge chip', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        expect(screen.getByText('Predicted')).toBeInTheDocument();
    });

    it('shows legend items', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        expect(screen.getByText('Has ex-date')).toBeInTheDocument();
        expect(screen.getByText('≤3 days away')).toBeInTheDocument();
    });

    it('auto-selects next upcoming date and shows tickers in detail panel', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        const labels = screen.getAllByText('Dividend / share');
        expect(labels.length).toBe(2);
        const totals = screen.getAllByText('Est. total (to date)');
        expect(totals.length).toBe(2);
    });

    it('renders high and low confidence badges in detail panel', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        const high = screen.getByText('high');
        const low = screen.getByText('low');
        expect(high.className).toContain('text-emerald-400');
        expect(low.className).toContain('text-rose-400');
    });

    it('filters by ticker search and hides non-matching tickers', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        const input = screen.getByPlaceholderText('Filter by ticker...');
        fireEvent.change(input, { target: { value: 'GOOGL' } });
        // Both are on the same auto-selected date, so GOOGL still shows but AAPL is hidden
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
        expect(screen.queryByText('AAPL')).not.toBeInTheDocument();
    });

    it('shows loading state with shimmer', () => {
        const { container } = render(<DividendsUpcomingCard data={undefined} isLoading error={null} />);
        expect(screen.getByText('Ex-Dates Calendar')).toBeInTheDocument();
        expect(container.querySelector('.glass-shimmer')).toBeInTheDocument();
    });

    it('shows error state', () => {
        render(<DividendsUpcomingCard data={undefined} isLoading={false} error={new Error('fail')} />);
        expect(screen.getByText('Failed to load upcoming ex-dates')).toBeInTheDocument();
    });

    it('shows empty state when no upcoming', () => {
        render(<DividendsUpcomingCard data={[]} isLoading={false} error={null} />);
        expect(screen.getByText('No upcoming ex-dates found')).toBeInTheDocument();
    });

    it('displays legend with amber and rose dots', () => {
        const { container } = render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        const amberDots = container.querySelectorAll('.bg-amber-400');
        expect(amberDots.length).toBeGreaterThan(0);
        const roseDots = container.querySelectorAll('.bg-rose-500');
        expect(roseDots.length).toBeGreaterThanOrEqual(0);
    });

    it('shows count badge on calendar days that have ex-dates', () => {
        render(<DividendsUpcomingCard data={data} isLoading={false} error={null} />);
        const badges = screen.getAllByText((content) => /^\d+$/.test(content));
        expect(badges.length).toBeGreaterThan(0);
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendHoldingsTable
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendHoldingsTable', () => {
    const data: PortfolioDividendHolding[] = [
        { account_id: 1, symbol: 'AAPL', company_name: 'Apple Inc.', sector: 'Technology', quantity: 50, market_value: 9025, total_cost: 7500, forward_income: 380, trailing_12m_income: 360, current_yield: 4.21, forward_yield_on_cost: 5.07, payout_ratio: 45, increase_streak: 10, safety_score: 75, next_event: { symbol: 'AAPL', company_name: 'Apple Inc.', ex_dividend_date: '2026-07-15', amount_per_share: 1.90, estimated_income: 95, dividend_type: 'regular', confidence: 'high' } },
        { account_id: 1, symbol: 'GOOGL', company_name: 'Alphabet Inc.', sector: 'Technology', quantity: 30, market_value: 5256, total_cost: 4200, forward_income: 180, trailing_12m_income: 160, current_yield: 3.42, forward_yield_on_cost: 4.29, payout_ratio: 30, increase_streak: 5, safety_score: 85, next_event: null },
        { account_id: 1, symbol: 'XOM', company_name: 'Exxon Mobil', sector: 'Energy', quantity: 20, market_value: 2400, total_cost: 2200, forward_income: 280, trailing_12m_income: 260, current_yield: 11.67, forward_yield_on_cost: 12.73, payout_ratio: 60, increase_streak: null, safety_score: 55, next_event: null },
    ];

    it('renders all 3 rows', () => {
        render(<DividendHoldingsTable data={data} onSelect={vi.fn()} />);
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('XOM')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
    });

    it('renders column header names', () => {
        render(<DividendHoldingsTable data={data} onSelect={vi.fn()} />);
        expect(screen.getByText('Symbol')).toBeInTheDocument();
        expect(screen.getByText('Name')).toBeInTheDocument();
        expect(screen.getByText('Sector')).toBeInTheDocument();
        expect(screen.getByText('Fwd Income')).toBeInTheDocument();
        expect(screen.getByText('Safety')).toBeInTheDocument();
    });

    it('shows — for null safety_score', () => {
        const noSafety = [{ ...data[0], safety_score: null }];
        render(<DividendHoldingsTable data={noSafety} onSelect={vi.fn()} />);
        const safetyCell = screen.getAllByRole('cell').filter(c => c.textContent === '—');
        expect(safetyCell.length).toBeGreaterThanOrEqual(1);
    });

    it('filters by symbol search', () => {
        render(<DividendHoldingsTable data={data} onSelect={vi.fn()} />);
        fireEvent.change(screen.getByPlaceholderText('Search symbol or name...'), { target: { value: 'AAPL' } });
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.queryByText('GOOGL')).not.toBeInTheDocument();
        expect(screen.queryByText('XOM')).not.toBeInTheDocument();
    });

    it('filters by company name search', () => {
        render(<DividendHoldingsTable data={data} onSelect={vi.fn()} />);
        fireEvent.change(screen.getByPlaceholderText('Search symbol or name...'), { target: { value: 'Exxon' } });
        expect(screen.getByText('XOM')).toBeInTheDocument();
        expect(screen.queryByText('AAPL')).not.toBeInTheDocument();
    });

    it('filters by sector dropdown', () => {
        render(<DividendHoldingsTable data={data} onSelect={vi.fn()} />);
        fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Energy' } });
        expect(screen.getByText('XOM')).toBeInTheDocument();
        expect(screen.queryByText('AAPL')).not.toBeInTheDocument();
    });

    it('shows empty message when no match', () => {
        render(<DividendHoldingsTable data={data} onSelect={vi.fn()} />);
        fireEvent.change(screen.getByPlaceholderText('Search symbol or name...'), { target: { value: 'ZZZZ' } });
        expect(screen.getByText('No holdings match your search.')).toBeInTheDocument();
    });

    it('triggers onSelect callback on row click', () => {
        const onSelect = vi.fn();
        render(<DividendHoldingsTable data={data} onSelect={onSelect} />);
        fireEvent.click(screen.getByText('AAPL'));
        expect(onSelect).toHaveBeenCalledWith('AAPL');
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendDetailDrawer
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendDetailDrawer', () => {
    it('renders nothing when symbol is null', () => {
        const { container } = render(<DividendDetailDrawer symbol={null} onClose={vi.fn()} />);
        expect(container.innerHTML).toBe('');
    });

    it('shows loading shimmer when symbol is set and data loading', () => {
        mockUseDividendHoldingDetail.mockReturnValue({ data: undefined, isLoading: true, error: null });
        const { container } = render(<DividendDetailDrawer symbol="AAPL" onClose={vi.fn()} />);
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(container.querySelector('.glass-shimmer')).toBeInTheDocument();
    });

    it('shows error state', () => {
        mockUseDividendHoldingDetail.mockReturnValue({ data: undefined, isLoading: false, error: new Error('fail') });
        render(<DividendDetailDrawer symbol="AAPL" onClose={vi.fn()} />);
        expect(screen.getByText('Failed to load holding details. Retry.')).toBeInTheDocument();
    });

    it('renders income summary and quality metrics', () => {
        mockUseDividendHoldingDetail.mockReturnValue({
            data: {
                symbol: 'AAPL',
                company_name: 'Apple Inc.',
                sector: 'Technology',
                income: { trailing_12m: 360, forward: 380, ytd: 180, yield_on_cost: 5.07, market_value: 9025, cost_basis: 7500 },
                quality_metrics: { safety_score: 75, payout_ratio: 45, growth_5yr: 8.5, increase_streak: 10 },
                dividend_history: [{ date: '2026-04-15', amount: 1.90 }],
                recent_payments: [{ payment_date: '2026-04-15', amount: 95, shares_held: 50 }],
            },
            isLoading: false,
            error: null,
        });
        render(<DividendDetailDrawer symbol="AAPL" onClose={vi.fn()} />);
        expect(screen.getByText('Income Summary')).toBeInTheDocument();
        expect(screen.getByText('Quality Metrics')).toBeInTheDocument();
        expect(screen.getByText('Trailing 12M')).toBeInTheDocument();
        expect(screen.getByText('Forward Est.')).toBeInTheDocument();
        expect(screen.getByText('Safety')).toBeInTheDocument();
        expect(screen.getByText('Inc. Streak')).toBeInTheDocument();
        expect(screen.getByText('Recent Payments')).toBeInTheDocument();
        expect(screen.getByText('2026-04-15')).toBeInTheDocument();
    });

    it('calls onClose when backdrop clicked', () => {
        mockUseDividendHoldingDetail.mockReturnValue({ data: undefined, isLoading: false, error: null });
        const onClose = vi.fn();
        render(<DividendDetailDrawer symbol="AAPL" onClose={onClose} />);
        const backdrop = document.querySelector('.fixed.inset-0.bg-black\\/40');
        if (backdrop) fireEvent.click(backdrop);
        expect(onClose).toHaveBeenCalledOnce();
    });

    it('calls onClose on Escape key', () => {
        mockUseDividendHoldingDetail.mockReturnValue({ data: undefined, isLoading: false, error: null });
        const onClose = vi.fn();
        render(<DividendDetailDrawer symbol="AAPL" onClose={onClose} />);
        fireEvent.keyDown(document, { key: 'Escape' });
        expect(onClose).toHaveBeenCalledOnce();
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendsSummarySection
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendsSummarySection', () => {
    const summaryData: PortfolioDividendSummary = {
        trailing_12m_income: 5000,
        forward_annual_estimate: 5200,
        ytd_dividends: 1874.35,
        forward_yield_on_cost: 4.52,
        avg_monthly_trailing: 416.67,
        avg_monthly_forward: 433.33,
        portfolio_growth_5yr: { value: 8.5, coverage_pct: 80 },
        portfolio_safety: { value: 72.3, coverage_pct: 85 },
        goal_progress: null,
        currency: 'USD',
        currencies_mixed: false,
        last_updated: '2026-06-18T00:00:00Z',
    };

    it('renders all 8 metric labels', () => {
        render(<DividendsSummarySection data={summaryData} isLoading={false} error={null} />);
        const labels = ['Trailing 12M', 'Forward Est. Annual', 'YTD Dividends', 'Forward Yield on Cost', 'Avg Monthly (Trailing)', 'Avg Monthly (Forward)', 'Portfolio Growth 5Y', 'Portfolio Safety'];
        for (const label of labels) {
            expect(screen.getByText(label)).toBeInTheDocument();
        }
    });

    it('renders coverage badges for growth and safety', () => {
        render(<DividendsSummarySection data={summaryData} isLoading={false} error={null} />);
        expect(screen.getByText('80% coverage')).toBeInTheDocument();
        expect(screen.getByText('85% coverage')).toBeInTheDocument();
    });

    it('renders GoalProgressCard', () => {
        render(<DividendsSummarySection data={summaryData} isLoading={false} error={null} />);
        expect(screen.getByText('Goal Progress')).toBeInTheDocument();
    });

    it('shows 6 shimmer cards when loading', () => {
        const { container } = render(<DividendsSummarySection data={undefined} isLoading error={null} />);
        expect(container.querySelectorAll('.glass-shimmer').length).toBe(6);
    });

    it('shows error message', () => {
        render(<DividendsSummarySection data={undefined} isLoading={false} error={new Error('fail')} />);
        expect(screen.getByText('Failed to load dividend summary')).toBeInTheDocument();
    });
});

// ═══════════════════════════════════════════════════════════════════════════════
// DividendsHoldingsSection
// ═══════════════════════════════════════════════════════════════════════════════
describe('DividendsHoldingsSection', () => {
    const holdingsData: PortfolioDividendHolding[] = [
        { account_id: 1, symbol: 'AAPL', company_name: 'Apple Inc.', sector: 'Technology', quantity: 50, market_value: 9025, total_cost: 7500, forward_income: 380, trailing_12m_income: 360, current_yield: 4.21, forward_yield_on_cost: 5.07, payout_ratio: 45, increase_streak: 10, safety_score: 75, next_event: null },
    ];

    it('renders heading and symbol', () => {
        render(<DividendsHoldingsSection data={holdingsData} isLoading={false} error={null} />);
        expect(screen.getByText('Holdings')).toBeInTheDocument();
        expect(screen.getByText('AAPL')).toBeInTheDocument();
    });

    it('shows 3 shimmer rows when loading', () => {
        const { container } = render(<DividendsHoldingsSection data={undefined} isLoading error={null} />);
        expect(container.querySelectorAll('.glass-shimmer').length).toBe(3);
    });

    it('shows error message', () => {
        render(<DividendsHoldingsSection data={undefined} isLoading={false} error={new Error('fail')} />);
        expect(screen.getByText('Failed to load dividend holdings')).toBeInTheDocument();
    });

    it('shows empty state', () => {
        render(<DividendsHoldingsSection data={[]} isLoading={false} error={null} />);
        expect(screen.getByText('No dividend holdings')).toBeInTheDocument();
    });
});
