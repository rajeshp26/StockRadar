// web/src/features/portfolio/hooks/usePortfolio.ts

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useServices } from "@/shared/contexts/ServiceContext";
import { useToast } from "@/hooks/use-toast";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import type {
    Brokerage,
    PortfolioAccount,
    PortfolioOverview,
    Holding,
    AggregatedHolding,
    ImportTransactionsRequest,
    ImportStatusResponse,
    PerformanceResponse,
    BenchmarkInfo,
    BenchmarkCompareResponse,
    PortfolioAllocationResponse,
    Transaction,
    TransactionFilter,
    DividendDetail,
    DividendHistoryResponse,
    MonthlyDividendSummary,
    PortfolioDividendSummary,
    PortfolioDividendHolding,
    PortfolioDividendHoldingDetail,
    UpcomingExDate,
    RiskMetricsResponse,
    DrawdownResponse,
    CovarianceResponse,
    EfficientFrontierResponse,
    RollingSharpeResponse,
    RiskContributionResponse,
    FactorExposureResponse,
    HoldingExistsResponse,
    HoldingPerformanceResponse,
    HoldingDividendSummary,
    HoldingTransaction,
    HoldingAccountBreakdown,
    TimePeriod,
} from "../types/portfolio.types";

/**
 * Hook for portfolio overview data
 * @param accountIds - optional account filter (pass first ID to backend)
 */
export function usePortfolioOverview(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const accountId = accountIds?.[0];

    return useQuery<PortfolioOverview, Error>({
        queryKey: [...QK.portfolioOverview(), accountId].filter(Boolean),
        queryFn: () => portfolioService.getPortfolioOverview(accountId),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for user's portfolio accounts
 */
export function usePortfolioAccounts() {
    const { portfolioService } = useServices();

    return useQuery<PortfolioAccount[], Error>({
        queryKey: QK.portfolioAccounts(),
        queryFn: () => portfolioService.getAccounts(),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for holdings across all accounts
 */
export function useAllHoldings() {
    const { portfolioService } = useServices();

    return useQuery<Holding[], Error>({
        queryKey: QK.portfolioHoldings(),
        queryFn: () => portfolioService.getAllHoldings() as Promise<Holding[]>,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for aggregated holdings (grouped by symbol across accounts)
 *
 * Returns one row per symbol with combined quantity, weighted avg cost,
 * and per-account breakdown.
 */
export function useAggregatedHoldings() {
    const { portfolioService } = useServices();

    return useQuery<AggregatedHolding[], Error>({
        queryKey: [...QK.portfolioHoldings(), "aggregated"],
        queryFn: () => portfolioService.getAllHoldings(true) as Promise<AggregatedHolding[]>,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        refetchOnWindowFocus: true,
    });
}

/**
 * Hook for account-specific holdings
 */
export function useAccountHoldings(accountId: number | null) {
    const { portfolioService } = useServices();

    return useQuery({
        queryKey: QK.portfolioAccountHoldings(accountId!),
        queryFn: () => portfolioService.getAccountHoldings(accountId!),
        enabled: accountId !== null,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for supported brokerages
 */
export function useBrokerages() {
    const { portfolioService } = useServices();

    return useQuery<Brokerage[], Error>({
        queryKey: QK.portfolioBrokerages(),
        queryFn: () => portfolioService.getBrokerages(),
        staleTime: STALE.STATIC, // Brokerages rarely change
        gcTime: GC.STATIC,
        retry: 1,
    });
}

/**
 * Hook for importing transactions
 */
export function useImportTransactions() {
    const { portfolioService } = useServices();
    const { toast } = useToast();

    return useMutation({
        mutationFn: async (request: ImportTransactionsRequest) => {
            return portfolioService.importTransactions(request);
        },
        onError: (error: Error) => {
            toast({
                title: "Import Error",
                description: error.message || "An error occurred during import",
                variant: "destructive",
            });
        },
    });
}

/**
 * Hook for deleting an account
 */
export function useDeleteAccount() {
    const { portfolioService } = useServices();
    const queryClient = useQueryClient();
    const { toast } = useToast();

    return useMutation({
        mutationFn: (accountId: number) => portfolioService.deleteAccount(accountId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: QK.portfolioOverview() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioAccounts() });
            queryClient.invalidateQueries({ queryKey: QK.portfolioHoldings() });

            toast({
                title: "Account Deleted",
                description: "Account and all associated data have been removed.",
            });
        },
        onError: (error: Error) => {
            toast({
                title: "Delete Failed",
                description: error.message || "Failed to delete account",
                variant: "destructive",
            });
        },
    });
}

/**
 * Hook for portfolio performance time series
 */
export function usePortfolioPerformance(period: string = "1Y", accountIds?: number[]) {
    const { portfolioService } = useServices();
    const idsParam = accountIds && accountIds.length > 0
        ? [...accountIds].sort().join(",")
        : undefined;

    return useQuery<PerformanceResponse, Error>({
        queryKey: QK.portfolioPerformance(period, idsParam),
        queryFn: () => portfolioService.getPortfolioPerformance(period, idsParam),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook for available benchmarks
 */
export function useBenchmarks() {
    const { portfolioService } = useServices();

    return useQuery<BenchmarkInfo[], Error>({
        queryKey: QK.portfolioBenchmarks(),
        queryFn: () => portfolioService.getBenchmarks(),
        staleTime: STALE.STATIC,
        gcTime: GC.STATIC,
        retry: 1,
    });
}

/**
 * Hook for benchmark comparison data
 */
export function useBenchmarkCompare(period: string, benchmarks: string[], accountIds?: number[]) {
    const { portfolioService } = useServices();
    const idsParam = accountIds && accountIds.length > 0
        ? [...accountIds].sort().join(",")
        : undefined;

    return useQuery<BenchmarkCompareResponse, Error>({
        queryKey: QK.portfolioBenchmarkCompare(period, benchmarks, idsParam),
        queryFn: () => portfolioService.getBenchmarkCompare(period, benchmarks, idsParam),
        enabled: benchmarks.length > 0,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook for polling import job status
 */
export function useImportStatus(importBatchId: string | null) {
    const { portfolioService } = useServices();

    return useQuery<ImportStatusResponse, Error>({
        queryKey: ['portfolio', 'import-status', importBatchId],
        queryFn: () => portfolioService.getImportStatus(importBatchId!),
        enabled: !!importBatchId,
        refetchInterval: (query) => {
            const status = query.state.data?.status;
            if (status === 'completed' || status === 'failed') {
                return false;
            }
            return 2000;
        },
        staleTime: 1000,
        gcTime: 0,
    });
}

/**
 * Hook: check if user holds a position in the given symbol
 */
export function useHoldingExists(symbol: string) {
    const { portfolioService } = useServices();
    return useQuery<HoldingExistsResponse, Error>({
        queryKey: QK.holdingExists(symbol),
        queryFn: () => portfolioService.checkHoldingExists(symbol),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
    });
}

/**
 * Hook: time-series performance for a single held stock
 */
export function useHoldingPerformance(symbol: string, period: TimePeriod = "1Y") {
    const { portfolioService } = useServices();
    return useQuery<HoldingPerformanceResponse, Error>({
        queryKey: QK.holdingPerformance(symbol, period),
        queryFn: () => portfolioService.getHoldingPerformance(symbol, period),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook: dividend history for a single held stock (quarterly aggregates)
 */
export function useHoldingDividends(symbol: string) {
    const { portfolioService } = useServices();
    return useQuery<HoldingDividendSummary[], Error>({
        queryKey: QK.holdingDividends(symbol),
        queryFn: () => portfolioService.getHoldingDividends(symbol),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
    });
}

/**
 * Hook: transaction history for a single held stock (P-04)
 */
export function useHoldingTransactions(symbol: string) {
    const { portfolioService } = useServices();
    return useQuery<HoldingTransaction[], Error>({
        queryKey: QK.holdingTransactions(symbol),
        queryFn: () => portfolioService.getHoldingTransactions(symbol),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
    });
}

/**
 * Hook: per-account breakdown for a single held stock (P-05)
 */
export function useHoldingAccounts(symbol: string) {
    const { portfolioService } = useServices();
    return useQuery<HoldingAccountBreakdown[], Error>({
        queryKey: QK.holdingAccounts(symbol),
        queryFn: () => portfolioService.getHoldingAccounts(symbol),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
    });
}

/**
 * Hook: holding-level benchmark comparison (P-03)
 */
export function useHoldingBenchmarkCompare(
    symbol: string,
    period: TimePeriod,
    benchmarks: string[],
) {
    const { portfolioService } = useServices();
    return useQuery<BenchmarkCompareResponse, Error>({
        queryKey: QK.holdingBenchmarkCompare(symbol, period, benchmarks),
        queryFn: () => portfolioService.getHoldingBenchmarkCompare(symbol, period, benchmarks),
        enabled: benchmarks.length > 0,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        placeholderData: (previousData) => previousData,
    });
}

/**
 * Hook for portfolio allocation data
 */
export function usePortfolioAllocation(groupBy: string = "sector", accountIds?: number[]) {
    const { portfolioService } = useServices();
    const idsParam = accountIds && accountIds.length > 0
        ? [...accountIds].sort().join(",")
        : undefined;

    return useQuery<PortfolioAllocationResponse, Error>({
        queryKey: QK.portfolioAllocation(groupBy, idsParam),
        queryFn: () => portfolioService.getPortfolioAllocation(groupBy, idsParam),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for aggregated dividends across all (or specified) accounts.
 * When accountIds is undefined, returns data for ALL accounts.
 * When specified, returns data only for those accounts.
 */
export function useAllDividends(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const idsParam = accountIds && accountIds.length > 0
        ? [...accountIds].sort().join(",")
        : undefined;

    return useQuery<{
        account_id?: number;
        current_year_total: number;
        monthly_summaries: MonthlyDividendSummary[];
    }, Error>({
        queryKey: QK.portfolioAllDividends(idsParam),
        queryFn: () => portfolioService.getAllDividends(idsParam),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

// ========================================================================
// DIVIDEND DASHBOARD HOOKS
// ========================================================================

const DASHBOARD_STALE = 5 * 60 * 1000;
const UPCOMING_STALE = 60 * 60 * 1000;

export function useDividendSummary(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<PortfolioDividendSummary, Error>({
        queryKey: QK.dividendDashboardSummary(ids ?? ""),
        queryFn: () => portfolioService.getDividendDashboardSummary(ids),
        staleTime: DASHBOARD_STALE,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useDividendUpcoming(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<UpcomingExDate[], Error>({
        queryKey: QK.dividendDashboardUpcoming(ids ?? ""),
        queryFn: () => portfolioService.getDividendDashboardUpcoming(ids),
        staleTime: UPCOMING_STALE,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useDividendHoldings(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<PortfolioDividendHolding[], Error>({
        queryKey: QK.dividendDashboardHoldings(ids ?? ""),
        queryFn: () => portfolioService.getDividendDashboardHoldings(ids),
        staleTime: DASHBOARD_STALE,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useDividendHoldingDetail(symbol: string | null, accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<PortfolioDividendHoldingDetail, Error>({
        queryKey: QK.dividendDashboardHoldingDetail(symbol ?? "", ids ?? ""),
        queryFn: () => portfolioService.getDividendDashboardHoldingDetail(symbol!, ids),
        enabled: !!symbol,
        staleTime: DASHBOARD_STALE,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for account dividend monthly summaries
 */
export function useAccountDividends(accountId: number | null) {
    const { portfolioService } = useServices();

    return useQuery<{
        account_id: number;
        current_year_total: number;
        monthly_summaries: MonthlyDividendSummary[];
    }, Error>({
        queryKey: QK.portfolioAccountDividends(accountId!),
        queryFn: () => portfolioService.getAccountDividends(accountId!),
        enabled: accountId !== null,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for extended dividend history
 */
export function useDividendHistory(accountId: number | null) {
    const { portfolioService } = useServices();

    return useQuery<DividendHistoryResponse, Error>({
        queryKey: QK.portfolioDividendHistory(accountId!),
        queryFn: () => portfolioService.getDividendHistory(accountId!),
        enabled: accountId !== null,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for transactions across all (or specified) accounts.
 * When accountIds is undefined, returns data for ALL accounts.
 * Supports the same TransactionFilter as the per-account hook.
 */
export function useAllTransactions(
    accountIds?: number[],
    filter?: TransactionFilter
) {
    const { portfolioService } = useServices();
    const idsParam = accountIds && accountIds.length > 0
        ? [...accountIds].sort().join(",")
        : undefined;
    const filterKey = JSON.stringify(filter || {});

    return useQuery<{
        transactions: Transaction[];
        total_count: number;
    }, Error>({
        queryKey: QK.portfolioAllTransactions(idsParam, filterKey),
        queryFn: () => portfolioService.getAllTransactions(idsParam, filter),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for filtered account transactions
 */
export function useAccountTransactionsFiltered(
    accountId: number | null,
    filter?: TransactionFilter
) {
    const { portfolioService } = useServices();
    const filterKey = JSON.stringify(filter || {});

    return useQuery<{
        account_id: number;
        transactions: Transaction[];
        total_count: number;
    }, Error>({
        queryKey: QK.portfolioAccountTransactionsFiltered(accountId!, filterKey),
        queryFn: () => portfolioService.getAccountTransactionsFiltered(accountId!, filter),
        enabled: accountId !== null,
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

// ========================================================================
// RISK METRICS HOOKS
// ========================================================================

const idsParam = (accountIds?: number[]) =>
    accountIds && accountIds.length > 0 ? [...accountIds].sort().join(",") : undefined;

export function useRiskMetrics(period: string = "1Y", accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<RiskMetricsResponse, Error>({
        queryKey: QK.riskMetrics(period, ids),
        queryFn: () => portfolioService.getRiskMetrics(period, ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useDrawdown(period: string = "1Y", accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<DrawdownResponse, Error>({
        queryKey: QK.drawdown(period, ids),
        queryFn: () => portfolioService.getDrawdown(period, ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useCovariance(period: string = "1Y", accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<CovarianceResponse, Error>({
        queryKey: QK.covariance(period, ids),
        queryFn: () => portfolioService.getCovariance(period, ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useEfficientFrontier(points: number = 20, accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<EfficientFrontierResponse, Error>({
        queryKey: QK.efficientFrontier(points, ids),
        queryFn: () => portfolioService.getEfficientFrontier(points, ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useRollingSharpe(window: number = 60, period: string = "1Y", accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<RollingSharpeResponse, Error>({
        queryKey: QK.rollingSharpe(window, period, ids),
        queryFn: () => portfolioService.getRollingSharpe(window, period, ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

export function useRiskContribution(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<RiskContributionResponse, Error>({
        queryKey: QK.riskContribution(ids),
        queryFn: () => portfolioService.getRiskContribution(ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}

/**
 * Hook for stock price history (sparkline data)
 */
export function usePriceHistory(symbol: string | null, days: number = 30) {
    const { portfolioService } = useServices();

    return useQuery({
        queryKey: ['price-history', symbol, days],
        queryFn: () => portfolioService.getPriceHistory(symbol!, days),
        enabled: !!symbol,
        staleTime: 2 * 60 * 1000,
        gcTime: 5 * 60 * 1000,
        retry: 1,
    });
}

/**
 * Hook for stock news articles
 */
export function useStockNews(symbol: string | null, limit: number = 10) {
    const { portfolioService } = useServices();

    return useQuery({
        queryKey: ['stock-news', symbol, limit],
        queryFn: () => portfolioService.getStockNews(symbol!, limit),
        enabled: !!symbol,
        staleTime: 5 * 60 * 1000,
        gcTime: 10 * 60 * 1000,
        retry: 1,
    });
}

export function useMarketExposure(accountIds?: number[]) {
    const { portfolioService } = useServices();
    const ids = idsParam(accountIds);

    return useQuery<FactorExposureResponse, Error>({
        queryKey: QK.marketExposure(ids),
        queryFn: () => portfolioService.getMarketExposure(ids),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
        retry: 1,
    });
}