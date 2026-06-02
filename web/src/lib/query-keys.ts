// web/src/lib/query-keys.ts
import type { DdmVariant } from "@/features/analysis/types/analysis.types";
/**
 * Centralized query key factory.
 *
 * Design rules:
 *  1. Keys are hierarchical arrays — invalidating a prefix busts all children.
 *     e.g. invalidate ["valuation", "rule1"] → clears all Rule #1 symbols.
 *  2. Symbols are always uppercased — "aapl" and "AAPL" share the same entry.
 *  3. All keys are `as const` tuples for TypeScript narrowing.
 */
export const QK = {
  // ── Analysis valuations ──────────────────────────────────────────────────
  rule1: (symbol: string) =>
    ["valuation", "rule1", symbol.toUpperCase()] as const,
  dividend: (symbol: string) =>
    ["valuation", "dividend", symbol.toUpperCase()] as const,
  rule1History: (symbol: string) =>
    ["valuation", "rule1", "history", symbol.toUpperCase()] as const,
  dcf: (symbol: string) =>
    ["valuation", "dcf", symbol.toUpperCase()] as const,
  dcfHistory: (symbol: string) =>
    ["valuation", "dcf", "history", symbol.toUpperCase()] as const,
  ddm: (symbol: string, variant: DdmVariant) =>
    ["valuation", "ddm", symbol.toUpperCase(), variant] as const,
  ddmHistory: (symbol: string, variant: DdmVariant) =>
    ["valuation", "ddm", "history", symbol.toUpperCase(), variant] as const,
  ownerEarnings: (symbol: string) =>
    ["valuation", "ownerEarnings", symbol.toUpperCase()] as const,
  ownerEarningsHistory: (symbol: string) =>
    ["valuation", "ownerEarnings", "history", symbol.toUpperCase()] as const,
  residualIncome: (symbol: string) =>
    ["valuation", "residualIncome", symbol.toUpperCase()] as const,
  residualIncomeHistory: (symbol: string) =>
    ["valuation", "residualIncome", "history", symbol.toUpperCase()] as const,
  // ── Valuation overview (cross-method AI recommendation) ──────────────────
  overview: (symbol: string) =>
    ["valuation", "overview", symbol.toUpperCase()] as const,
  // ── Live price ───────────────────────────────────────────────────────────
  price: (symbol: string) =>
    ["price", symbol.toUpperCase()] as const,
  // ── Watchlist structure (stocks + targets for one list) ──────────────────
  watchlist: (id: number | "default") =>
    ["watchlist", id] as const,
  // ── All watchlists metadata (switcher, cap check) ────────────────────────
  watchlists: () =>
    ["watchlists"] as const,
  magicFormula: (symbol: string) =>
    ["analysis", "magic-formula", symbol.toUpperCase()] as const,
  canslim: (symbol: string) =>
    ["analysis", "canslim", symbol.toUpperCase()] as const,
  murphyTechnical: (symbol: string) =>
    ["analysis", "technical", "murphy", symbol.toUpperCase()] as const,
  moat: (symbol: string) =>
    ["analysis", "moat", symbol.toUpperCase()] as const,
  stockVsIndex: (symbol: string, benchmarkSymbols: string[], years: number) => ["stock-vs-index", symbol, ...benchmarkSymbols, years] as const,
  superInvestors: (symbol: string) =>
    ["analysis", "super-investors", symbol.toUpperCase()] as const,
  // ── Standalone Super Investors page ─────────────────────────────────────
  superInvestorsOverview: () =>
    ["super-investors", "overview"] as const,
  superInvestorsTopStocks: (sector?: string, style?: string, minInvestors?: number) =>
    ["super-investors", "top-stocks", sector ?? "", style ?? "", minInvestors ?? 1] as const,
  superInvestorsOverlap: (minInvestors?: number, sector?: string) =>
    ["super-investors", "overlap", minInvestors ?? 3, sector ?? ""] as const,
  superInvestorsActivity: (changeType?: string, investorTag?: string, quarters?: number) =>
    ["super-investors", "activity", changeType ?? "", investorTag ?? "", quarters ?? 4] as const,
  superInvestorsList: () =>
    ["super-investors", "investors"] as const,
  superInvestorPortfolio: (tag: string, quarters?: number) =>
    ["super-investors", "investors", tag.toUpperCase(), quarters ?? 8] as const,
  superInvestorsSectors: (style?: string) =>
    ["super-investors", "sectors", style ?? ""] as const,
  riskAssessment: (symbol: string) =>
    ["analysis", "risk-assessment", symbol.toUpperCase()] as const,
  // Portfolio
  portfolioOverview: () =>
    ["portfolio", "overview"] as const,
  portfolioAccounts: () =>
    ["portfolio", "accounts"] as const,
  portfolioHoldings: () =>
    ["portfolio", "holdings"] as const,
  portfolioAccountHoldings: (accountId: number) =>
    ["portfolio", "account", accountId, "holdings"] as const,
  portfolioBrokerages: () =>
    ["portfolio", "brokerages"] as const,
  portfolioAccountTransactions: (accountId: number, limit: number = 100) =>
    ["portfolio", "account", accountId, "transactions", limit] as const,
  portfolioAccountDividends: (accountId: number) =>
    ["portfolio", "account", accountId, "dividends"] as const,
  portfolioAllDividends: (accountIds?: string) =>
    accountIds
      ? ["portfolio", "dividends", accountIds] as const
      : ["portfolio", "dividends"] as const,
  portfolioPerformance: (period: string, accountIds?: string) =>
    accountIds
      ? ["portfolio", "performance", period, accountIds] as const
      : ["portfolio", "performance", period] as const,
  portfolioBenchmarks: () =>
    ["portfolio", "benchmarks"] as const,
  portfolioBenchmarkCompare: (period: string, benchmarks: string[], accountIds?: string) =>
    accountIds
      ? ["portfolio", "benchmark-compare", period, ...benchmarks, accountIds] as const
      : ["portfolio", "benchmark-compare", period, ...benchmarks] as const,
  portfolioAllocation: (groupBy: string, accountIds?: string) =>
    accountIds
      ? ["portfolio", "allocation", groupBy, accountIds] as const
      : ["portfolio", "allocation", groupBy] as const,
  portfolioDividendHistory: (accountId: number) =>
    ["portfolio", "account", accountId, "dividend-history"] as const,
  portfolioAccountTransactionsFiltered: (accountId: number, filter: string) =>
    ["portfolio", "account", accountId, "transactions", filter] as const,
  portfolioAllTransactions: (accountIds?: string, filter?: string) =>
    accountIds
      ? ["portfolio", "transactions", accountIds, filter] as const
      : ["portfolio", "transactions", filter] as const,
  // Portfolio Risk
  riskMetrics: (period: string, accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "metrics", period, accountIds] as const
      : ["portfolio", "risk", "metrics", period] as const,
  drawdown: (period: string, accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "drawdown", period, accountIds] as const
      : ["portfolio", "risk", "drawdown", period] as const,
  covariance: (period: string, accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "covariance", period, accountIds] as const
      : ["portfolio", "risk", "covariance", period] as const,
  efficientFrontier: (points: number, accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "frontier", points, accountIds] as const
      : ["portfolio", "risk", "frontier", points] as const,
  rollingSharpe: (window: number, period: string, accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "rolling-sharpe", window, period, accountIds] as const
      : ["portfolio", "risk", "rolling-sharpe", window, period] as const,
  riskContribution: (accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "contribution", accountIds] as const
      : ["portfolio", "risk", "contribution"] as const,
  marketExposure: (accountIds?: string) =>
    accountIds
      ? ["portfolio", "risk", "market-exposure", accountIds] as const
      : ["portfolio", "risk", "market-exposure"] as const,
} as const;