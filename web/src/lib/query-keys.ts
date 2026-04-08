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
} as const;