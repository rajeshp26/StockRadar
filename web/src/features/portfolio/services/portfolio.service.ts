// web/src/features/portfolio/services/portfolio.service.ts

import type { AxiosInstance } from "axios";
import api from "@/lib/api";
import type {
    Brokerage,
    PortfolioAccount,
    PortfolioOverview,
    Holding,
    AggregatedHolding,
    Transaction,
    MonthlyDividendSummary,
    ImportTransactionsRequest,
    ImportResult,
    ImportStatusResponse,
    AddManualTransactionRequest,
    AddManualTransactionResponse,
    PerformanceResponse,
    BenchmarkInfo,
    BenchmarkCompareResponse,
    PortfolioAllocationResponse,
    DividendDetail,
    DividendHistoryResponse,
    TransactionFilter,
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
    PortfolioDividendSummary,
    PortfolioDividendHolding,
    PortfolioDividendHoldingDetail,
    UpcomingExDate,
    PortfolioDashboardResponse,
} from "../types/portfolio.types";

/**
 * PortfolioService
 * 
 * API client for portfolio management following existing service patterns.
 * All calls go through Next.js proxy (/api/proxy/*).
 */
export class PortfolioService {
    private readonly api: AxiosInstance;

    constructor(client?: AxiosInstance) {
        this.api = client ?? api;
    }

    // ========================================================================
    // BROKERAGES
    // ========================================================================

    async getBrokerages(): Promise<Brokerage[]> {
        const res = await this.api.get<{ brokerages: Brokerage[] }>(
            "/portfolio/brokerages"
        );
        return res.data.brokerages;
    }

    // ========================================================================
    // ACCOUNTS
    // ========================================================================

    async getAccounts(): Promise<PortfolioAccount[]> {
        const res = await this.api.get<{ accounts: PortfolioAccount[] }>(
            "/portfolio/accounts"
        );
        return res.data.accounts;
    }

    async deleteAccount(accountId: number): Promise<void> {
        await this.api.delete(`/portfolio/accounts/${accountId}`);
    }

    // ========================================================================
    // DASHBOARD (bundle endpoint)
    // ========================================================================

    async getDashboardData(): Promise<PortfolioDashboardResponse> {
        const res = await this.api.get<PortfolioDashboardResponse>(
            "/portfolio/dashboard"
        );
        return res.data;
    }

    // ========================================================================
    // IMPORT
    // ========================================================================

    async importTransactions(
        request: ImportTransactionsRequest
    ): Promise<ImportResult> {
        const res = await this.api.post<ImportResult>(
            "/portfolio/import",
            request
        );
        return res.data;
    }

    async getImportStatus(
        importBatchId: string
    ): Promise<ImportStatusResponse> {
        const res = await this.api.get<ImportStatusResponse>(
            `/portfolio/import/${importBatchId}/status`
        );
        return res.data;
    }

    /**
     * Helper to convert File to base64-encoded string
     */
    async fileToBase64(file: File): Promise<string> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64 = reader.result as string;
                // Remove data URL prefix (data:text/csv;base64,)
                const base64Content = base64.split(",")[1];
                resolve(base64Content);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    // ========================================================================
    // HOLDINGS
    // ========================================================================

    async getAccountHoldings(accountId: number): Promise<{
        account_id: number;
        account_name: string;
        holdings: Holding[];
    }> {
        const res = await this.api.get(
            `/portfolio/accounts/${accountId}/holdings`
        );
        return res.data;
    }

    async getAllHoldings(aggregated?: boolean): Promise<Holding[] | AggregatedHolding[]> {
        const params: Record<string, string> = {};
        if (aggregated) params.aggregated = "true";
        const res = await this.api.get<{ holdings: Holding[] | AggregatedHolding[] }>(
            "/portfolio/holdings",
            { params }
        );
        return res.data.holdings;
    }

    // ========================================================================
    // OVERVIEW
    // ========================================================================

    async getPortfolioOverview(accountId?: number): Promise<PortfolioOverview> {
        const params: Record<string, string | number> = {};
        if (accountId) params.account_id = accountId;
        const res = await this.api.get<PortfolioOverview>("/portfolio/overview", { params });
        return res.data;
    }

    // ========================================================================
    // TRANSACTIONS
    // ========================================================================

    async getAccountTransactions(
        accountId: number,
        limit: number = 100
    ): Promise<{
        account_id: number;
        transactions: Transaction[];
        total_count: number;
    }> {
        const res = await this.api.get(
            `/portfolio/accounts/${accountId}/transactions`,
            { params: { limit } }
        );
        return res.data;
    }

    // ========================================================================
    // MANUAL TRANSACTIONS
    // ========================================================================

    async addManualTransaction(
        request: AddManualTransactionRequest
    ): Promise<AddManualTransactionResponse> {
        const res = await this.api.post<AddManualTransactionResponse>(
            "/portfolio/transactions/manual",
            request
        );
        return res.data;
    }

    // ========================================================================
    // DIVIDENDS
    // ========================================================================

    async getAccountDividends(accountId: number): Promise<{
        account_id: number;
        current_year_total: number;
        monthly_summaries: MonthlyDividendSummary[];
    }> {
        const res = await this.api.get(
            `/portfolio/accounts/${accountId}/dividends`
        );
        return res.data;
    }

    async getAllDividends(accountIds?: string): Promise<{
        account_id?: number;
        current_year_total: number;
        monthly_summaries: MonthlyDividendSummary[];
    }> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get("/portfolio/dividends", { params });
        return res.data;
    }

    // ========================================================================
    // DIVIDEND DASHBOARD
    // ========================================================================

    async getDividendDashboardSummary(accountIds?: string): Promise<PortfolioDividendSummary> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<PortfolioDividendSummary>(
            "/portfolio/dividends/summary",
            { params }
        );
        return res.data;
    }

    async getDividendDashboardUpcoming(accountIds?: string): Promise<UpcomingExDate[]> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<UpcomingExDate[]>(
            "/portfolio/dividends/upcoming",
            { params }
        );
        return res.data;
    }

    async getDividendDashboardHoldings(accountIds?: string): Promise<PortfolioDividendHolding[]> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<PortfolioDividendHolding[]>(
            "/portfolio/dividends/holdings",
            { params }
        );
        return res.data;
    }

    async getDividendDashboardHoldingDetail(
        symbol: string,
        accountIds?: string
    ): Promise<PortfolioDividendHoldingDetail> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<PortfolioDividendHoldingDetail>(
            `/portfolio/dividends/holdings/${symbol}`,
            { params }
        );
        return res.data;
    }

    // ========================================================================
    // PERFORMANCE & BENCHMARKS
    // ========================================================================

    async getPortfolioPerformance(
        period: string = "1Y",
        accountIds?: string
    ): Promise<PerformanceResponse> {
        const params: Record<string, string> = { period };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<PerformanceResponse>(
            "/portfolio/performance",
            { params }
        );
        const snaps = res.data.snapshots ?? [];
        console.log(`[PERF] raw_api_response period=${period} rows=${snaps.length} ret=${res.data.totalReturnPct}% source=${res.data.dataSource}`);
        snaps.forEach(s => console.log(`[PERF]   date=${s.date} V=${s.value} ND=${s.netDeposits}`));
        return res.data;
    }

    // ========================================================================
    // HOLDING PERFORMANCE (single-stock)
    // ========================================================================

    async checkHoldingExists(symbol: string): Promise<HoldingExistsResponse> {
        const res = await this.api.get<HoldingExistsResponse>(
            `/portfolio/holdings/${symbol}/exists`
        );
        return res.data;
    }

    async getHoldingPerformance(
        symbol: string,
        period: string = "1Y"
    ): Promise<HoldingPerformanceResponse> {
        const res = await this.api.get<HoldingPerformanceResponse>(
            `/portfolio/holdings/${symbol}/performance`,
            { params: { period } }
        );
        return res.data;
    }

    async getHoldingDividends(symbol: string): Promise<HoldingDividendSummary[]> {
        const res = await this.api.get<HoldingDividendSummary[]>(
            `/portfolio/holdings/${symbol}/dividends`
        );
        return res.data;
    }

    async getHoldingTransactions(symbol: string): Promise<HoldingTransaction[]> {
        const res = await this.api.get<HoldingTransaction[]>(
            `/portfolio/holdings/${symbol}/transactions`
        );
        return res.data;
    }

    async getHoldingAccounts(symbol: string): Promise<HoldingAccountBreakdown[]> {
        const res = await this.api.get<HoldingAccountBreakdown[]>(
            `/portfolio/holdings/${symbol}/accounts`
        );
        return res.data;
    }

    async getHoldingBenchmarkCompare(
        symbol: string,
        period: string,
        benchmarks: string[]
    ): Promise<BenchmarkCompareResponse> {
        const params: Record<string, string> = { period, benchmarks: benchmarks.join(",") };
        const res = await this.api.get<BenchmarkCompareResponse>(
            `/portfolio/holdings/${symbol}/performance/compare`,
            { params }
        );
        return res.data;
    }

    async getBenchmarks(): Promise<BenchmarkInfo[]> {
        const res = await this.api.get<{ success: boolean; benchmarks: BenchmarkInfo[] }>(
            "/benchmarks"
        );
        return res.data.benchmarks;
    }

    async getBenchmarkCompare(
        period: string,
        benchmarks: string[],
        accountIds?: string
    ): Promise<BenchmarkCompareResponse> {
        const params: Record<string, string> = { period, benchmarks: benchmarks.join(",") };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<BenchmarkCompareResponse>(
            "/portfolio/performance/compare",
            { params }
        );
        return res.data;
    }

    // ========================================================================
    // ALLOCATION
    // ========================================================================

    async getPortfolioAllocation(
        groupBy: string = "sector",
        accountIds?: string
    ): Promise<PortfolioAllocationResponse> {
        const params: Record<string, string> = { group_by: groupBy };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<PortfolioAllocationResponse>(
            "/portfolio/allocation",
            { params }
        );
        return res.data;
    }

    // ========================================================================
    // DIVIDEND HISTORY (extended detail)
    // ========================================================================

    async getDividendHistory(accountId: number): Promise<DividendHistoryResponse> {
        const res = await this.api.get<DividendHistoryResponse>(
            `/portfolio/accounts/${accountId}/dividend-history`
        );
        return res.data;
    }

    // ========================================================================
    // TRANSACTIONS WITH FILTERS
    // ========================================================================

    async getAccountTransactionsFiltered(
        accountId: number,
        filter?: TransactionFilter,
        limit: number = 100
    ): Promise<{
        account_id: number;
        transactions: Transaction[];
        total_count: number;
    }> {
        const params: Record<string, string | number> = { limit };
        if (filter?.from_date) params.from_date = filter.from_date;
        if (filter?.to_date) params.to_date = filter.to_date;
        if (filter?.activity_type) params.activity_type = filter.activity_type;
        if (filter?.search) params.search = filter.search;
        const res = await this.api.get(
            `/portfolio/accounts/${accountId}/transactions`,
            { params }
        );
        return res.data;
    }

    async getAllTransactions(
        accountIds?: string,
        filter?: TransactionFilter,
        limit: number = 100
    ): Promise<{
        transactions: Transaction[];
        total_count: number;
    }> {
        const params: Record<string, string | number> = { limit };
        if (accountIds) params.account_ids = accountIds;
        if (filter?.from_date) params.from_date = filter.from_date;
        if (filter?.to_date) params.to_date = filter.to_date;
        if (filter?.activity_type) params.activity_type = filter.activity_type;
        if (filter?.search) params.search = filter.search;
        const res = await this.api.get("/portfolio/transactions", { params });
        return res.data;
    }

    // ========================================================================
    // PRICE HISTORY
    // ========================================================================

    async getPriceHistory(
        symbol: string,
        days: number = 30
    ): Promise<{
        success: boolean;
        symbol: string;
        days: number;
        data: { date: string; open: number | null; high: number | null; low: number | null; close: number | null; volume: number | null }[];
        error?: string;
    }> {
        const res = await this.api.get(`/stocks/${symbol}/price-history`, {
            params: { days },
        });
        return res.data;
    }

    // ========================================================================
    // STOCK NEWS
    // ========================================================================

    async getStockNews(
        symbol: string,
        limit: number = 10
    ): Promise<{
        success: boolean;
        symbol: string;
        articles: {
            uuid?: string;
            title: string;
            summary?: string;
            publisher: string;
            published_at: string;
            article_type: string;
            url?: string;
            related_symbols: string[];
        }[];
        source: string;
        error?: string;
    }> {
        const res = await this.api.get(`/stocks/${symbol}/news`, {
            params: { limit },
        });
        return res.data;
    }

    // ========================================================================
    // COMPANY SEARCH
    // ========================================================================

    async searchCompany(symbol: string): Promise<{ exists: boolean; company_name?: string }> {
        const res = await this.api.get<{ exists: boolean; company_name?: string }>(
            `/companies/search?symbol=${symbol}`
        );
        return res.data;
    }

    // ========================================================================
    // RISK METRICS
    // ========================================================================

    async getRiskMetrics(period: string = "1Y", accountIds?: string): Promise<RiskMetricsResponse> {
        const params: Record<string, string> = { period };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<RiskMetricsResponse>("/portfolio/risk-metrics", { params });
        return res.data;
    }

    async getDrawdown(period: string = "1Y", accountIds?: string): Promise<DrawdownResponse> {
        const params: Record<string, string> = { period };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<DrawdownResponse>("/portfolio/drawdown", { params });
        return res.data;
    }

    async getCovariance(period: string = "1Y", accountIds?: string): Promise<CovarianceResponse> {
        const params: Record<string, string> = { period };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<CovarianceResponse>("/portfolio/covariance", { params });
        return res.data;
    }

    async getEfficientFrontier(points: number = 20, accountIds?: string): Promise<EfficientFrontierResponse> {
        const params: Record<string, string> = { points: String(points) };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<EfficientFrontierResponse>("/portfolio/efficient-frontier", { params });
        return res.data;
    }

    async getRollingSharpe(window: number = 60, period: string = "1Y", accountIds?: string): Promise<RollingSharpeResponse> {
        const params: Record<string, string> = { window: String(window), period };
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<RollingSharpeResponse>("/portfolio/rolling-sharpe", { params });
        return res.data;
    }

    async getRiskContribution(accountIds?: string): Promise<RiskContributionResponse> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<RiskContributionResponse>("/portfolio/risk-contribution", { params });
        return res.data;
    }

    async getMarketExposure(accountIds?: string): Promise<FactorExposureResponse> {
        const params: Record<string, string> = {};
        if (accountIds) params.account_ids = accountIds;
        const res = await this.api.get<FactorExposureResponse>("/portfolio/market-exposure", { params });
        return res.data;
    }
}

export const portfolioService = new PortfolioService();