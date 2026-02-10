// src/features/analysis/types/analysis.types.ts

/**
 * Severity levels as emitted by backend diagnostics.
 * Matches ValuationService / Rule1 models.
 */
export type Severity = "critical" | "high" | "medium" | "low" | "info";

/**
 * Suitability categories rolled up from the backend score.
 */
export type SuitabilityCategory = "Good" | "Caution" | "Poor";

/**
 * One structured diagnostic about suitability, input quality, or assumptions.
 * FE renders: code badge, severity tone, message, optional evidence/recommendation.
 */
export interface DiagnosticFlag {
  code: string;
  severity: Severity;
  message: string;
  evidence?: Record<string, unknown>;
  recommendation?: string;
}

/**
 * Applicability summary: roll-up score, category, flags.
 */
export interface Applicability {
  score: number; // 0..100
  category: SuitabilityCategory;
  flags: DiagnosticFlag[];
}

/**
 * DataQuality bundle:
 * - freshnessDays: arbitrary key->value map (numbers, strings)
 *     keys we commonly expect:
 *       trailingEPS?: number  // days since snapshot
 *       epsForecast?: number  // days since last forecast report
 *       lastComputedAt?: string // ISO timestamp (we put it here for FE consistency)
 * - fallbacksUsed: true if any fallback path was used
 * - inputDecisions: traces of how inputs were chosen (and assumptions block)
 */
export interface DataQuality {
  freshnessDays: Record<string, unknown>;
  fallbacksUsed: boolean;
  inputDecisions: {
    eps0?: {
      value?: number | null;
      source?: string | null;
      snapshotDate?: string | null; // ISO date
    };
    growth?: {
      valueRaw?: number | null;
      valueClamped?: number | null;
      source?: string | null;
    };
    futurePE?: {
      selected?: number | null;
      rule?: string | null;
    };
    assumptions?: {
      discountRate?: number;
      horizonYears?: number;
      mos?: number;
    };
    // Allow backend to add more without breaking FE
    [k: string]: unknown;
  };
}

/**
 * Rule #1 valuation payload. Field names intentionally camelCase to match backend.
 */
export interface Rule1Valuation {
  symbol: string;
  companyId: number;
  currency: string;

  // Inputs (final)
  eps0: number;
  growth: number;
  futurePE: number;

  // Derived
  futureEPS: number;
  futurePrice: number;
  discountRate: number; // 0..1
  horizonYears: number; // usually 10
  mos: number;          // 0..1
  stickerPrice: number;
  mosPrice: number;
}

/**
 * Full response returned by POST /valuations/:symbol/rule1
 */
export interface Rule1Response {
  valuation: Rule1Valuation;
  applicability: Applicability;
  dataQuality: DataQuality;
}

/**
 * Minimal shape used to render rows in the (future) History table.
 * We’ll keep it optional for now since there’s no history endpoint yet.
 */
export interface Rule1HistoryEntry {
  runAt: string;
  stickerPrice?: number;
  mosPrice?: number;
  growth?: number;       // or growthRate if you standardize
  futurePE?: number;
  score?: number;
  category?: SuitabilityCategory;
}

export interface Rule1History {
  symbol: string;
  items: Rule1HistoryEntry[];
}

/**
 * API error envelope (standard FastAPI/your routes).
 */
export interface ApiError {
  detail: string;
}

/** ---------- FE Helper Types ---------- */

/**
 * Normalized freshness we show under “Last evaluated”.
 * We compute this client-side from DataQuality.freshnessDays.lastComputedAt or
 * the server’s IVA.last_updated (already attached by the cached path).
 */
export interface FreshnessInfo {
  lastEvaluatedDisplay?: string; // localized string for UI
  lastEvaluatedIso?: string;     // raw ISO timestamp if available
}

/**
 * ViewModel returned by the useAnalysis hook.
 * Keeps UI unaware of transport details.
 */
export interface AnalysisState {
  loading: boolean;
  loadingHistory: boolean;
  error?: string;

  valuation?: Rule1Valuation;
  applicability?: Applicability;
  dataQuality?: DataQuality;

  // optional placeholder until backend history is available
  history?: Rule1History;

  freshness?: FreshnessInfo;
}