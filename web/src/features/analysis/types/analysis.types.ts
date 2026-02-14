// web/src/features/analysis/types/analysis.types.ts

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type SuitabilityCategory = "Good" | "Caution" | "Poor";

export interface DiagnosticFlag {
  code: string;
  severity: Severity;
  message: string;
  evidence?: Record<string, unknown>;
  recommendation?: string;
}

export interface Applicability {
  score: number;
  category: SuitabilityCategory;
  flags: DiagnosticFlag[];
}

export interface DataQuality {
  freshnessDays: Record<string, unknown>;
  fallbacksUsed: boolean;
  inputDecisions: {
    eps0?: {
      value?: number | null;
      source?: string | null;
      snapshotDate?: string | null;
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
    [k: string]: unknown;
  };
}

export interface Rule1Valuation {
  symbol: string;
  companyId: number;
  currency: string;

  eps0: number;
  growth: number;
  futurePE: number;

  futureEPS: number;
  futurePrice: number;
  discountRate: number;
  horizonYears: number;
  mos: number;

  stickerPrice: number;
  mosPrice: number;
}

export interface Rule1Response {
  valuation: Rule1Valuation;
  applicability: Applicability;
  dataQuality: DataQuality;
}

export interface Rule1HistoryEntry {
  runAt: string;
  stickerPrice?: number;
  mosPrice?: number;
  futurePrice?: number;
  growth?: number;
  futurePE?: number;
  score?: number;
  category?: SuitabilityCategory;
}

export interface Rule1History {
  symbol: string;
  items: Rule1HistoryEntry[];
}

export interface ApiError {
  detail: string;
}

export interface FreshnessInfo {
  lastEvaluatedDisplay?: string;
  lastEvaluatedIso?: string;
}

export interface AnalysisState {
  loading: boolean;
  loadingHistory: boolean;
  error?: string;

  valuation?: Rule1Valuation;
  applicability?: Applicability;
  dataQuality?: DataQuality;

  history?: Rule1History;
  freshness?: FreshnessInfo;
}

/* ====================================================================== */
/* DDM TYPES                                                               */
/* ====================================================================== */

export type DdmVariant = "gordon" | "two_stage";

export interface DdmValuation {
  symbol: string;
  companyId: number;
  currency: string;
  method: "gordon" | "two_stage";

  currentDps: number;
  nextYearDps: number;
  dividendGrowthRate: number; // g
  requiredReturn: number;     // k
  intrinsicValue: number;

  highGrowthYears?: number | null;
  highGrowthRate?: number | null;
  stableGrowthRate?: number | null;
  pvStage1?: number | null;
  pvTerminal?: number | null;

  currentPrice?: number | null;
  upsideDownsidePct?: number | null;
}

export interface DdmResponse {
  valuation: DdmValuation;
  applicability: Applicability;
  dataQuality: DataQuality;
}

export interface DdmHistoryEntry {
  runAt: string;
  method?: "gordon" | "two_stage";
  intrinsicValue?: number;
  dividendGrowthRate?: number;
  requiredReturn?: number;
  score?: number;
  category?: SuitabilityCategory;
}

export interface DdmHistory {
  symbol: string;
  items: DdmHistoryEntry[];
}

export interface DdmState {
  loading: boolean;
  loadingHistory: boolean;
  error?: string;

  valuation?: DdmValuation;
  applicability?: Applicability;
  dataQuality?: DataQuality;

  history?: DdmHistory;
  freshness?: FreshnessInfo;
}