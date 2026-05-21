// web/src/features/portfolio/services/portfolio.service.ts

import type { AxiosInstance } from "axios";
import api from "@/lib/api";
import type {
    Brokerage,
    PortfolioAccount,
    PortfolioOverview,
    Holding,
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

    async getAllHoldings(): Promise<Holding[]> {
        const res = await this.api.get<{ holdings: Holding[] }>(
            "/portfolio/holdings"
        );
        return res.data.holdings;
    }

    // ========================================================================
    // OVERVIEW
    // ========================================================================

    async getPortfolioOverview(): Promise<PortfolioOverview> {
        const res = await this.api.get<PortfolioOverview>("/portfolio/overview");
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

    // ========================================================================
    // PERFORMANCE & BENCHMARKS
    // ========================================================================

    async getPortfolioPerformance(period: string = "1Y"): Promise<PerformanceResponse> {
        const res = await this.api.get<PerformanceResponse>(
            "/portfolio/performance",
            { params: { period } }
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
        benchmarks: string[]
    ): Promise<BenchmarkCompareResponse> {
        const res = await this.api.get<BenchmarkCompareResponse>(
            "/portfolio/performance/compare",
            { params: { period, benchmarks: benchmarks.join(",") } }
        );
        return res.data;
    }
}

export const portfolioService = new PortfolioService();