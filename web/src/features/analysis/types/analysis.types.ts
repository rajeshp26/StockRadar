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
  suitabilitySummary?: string | null;  // ← AI-generated plain-English explanation
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
  dividendGrowthRate: number;
  requiredReturn: number;
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
// ---------------------------
// DCF Types
// ---------------------------
export type DcfTerminalMethod = "perpetuity_growth" | "exit_multiple";
export interface DcfSensitivityGrid {
  discountRates: number[];
  terminalGrowthRates: number[];
  intrinsicValuePerShareMatrix: (number | null)[][];
  currency?: string | null;
}
export interface DcfValuation {
  symbol: string;
  companyId: number;
  currency: string;
  terminalMethod: DcfTerminalMethod;
  forecastYears: number;
  forecastFcf: number[];
  pvFcf: number[];
  totalPvFcf: number;
  discountFactors?: number[] | null;
  waccUsed: number;
  terminalValue?: number;
  pvTerminalValue?: number;
  terminalGrowthRateUsed?: number | null;
  cashFlowNPlus1?: number | null;
  baseFcf?: number | null;
  baseFcfFiscalYear?: number | null;
  enterpriseValue?: number;
  netDebtUsed?: number;
  equityValue?: number;
  sharesOutstanding?: number;
  intrinsicValuePerShare?: number;
  currentPrice?: number;
  upsideDownsidePct?: number;
  sensitivityScenarios?: DcfSensitivityGrid | null;
}
export interface DcfRequestOverrides {
  forecastYears?: number | null;
  forecastFcf?: number[] | null;
  fcfGrowthRate?: number | null;
  fcfMarginAssumption?: number | null;
  wacc?: number | null;
  terminalMethod?: DcfTerminalMethod | null;
  terminalGrowthRate?: number | null;
  exitMultiple?: number | null;
  terminalMetric?: "ebitda" | null;
  ebitdaMarginAssumption?: number | null;
  terminalEbitda?: number | null;
  sharesOutstanding?: number | null;
  netDebt?: number | null;
  analystName?: string | null;
  notes?: string | null;
}
export interface DcfResponse {
  valuation: DcfValuation;
  applicability: Applicability;
  dataQuality: DataQuality;
}
export interface DcfHistoryEntry {
  runAt: string;
  terminalMethod?: DcfTerminalMethod;
  intrinsicValuePerShare?: number;
  waccUsed?: number;
  terminalValue?: number;
  enterpriseValue?: number;
  score?: number;
  category?: SuitabilityCategory;
}
export interface DcfHistory {
  symbol: string;
  items: DcfHistoryEntry[];
}

/* ====================================================================== */
/* OWNER EARNINGS TYPES                                                    */
/* Buffett owner-earnings model:                                           */
/*   OE = Net Income + D&A − CapEx ± ΔWorking Capital                    */
/* ====================================================================== */

export interface OwnerEarningsValuation {
  symbol: string;
  companyId: number;
  currency: string;
  // Forecast parameters
  forecastYears: number;
  discountRateUsed: number;        // NOT "discountRate"
  oeGrowthRateUsed?: number | null; // NOT "growthRate"
  terminalGrowthRateUsed?: number | null; // NOT "terminalGrowthRate"
  maintenanceCapexRatioUsed?: number | null;
  // Base OE decomposition (waterfall transparency)
  baseOe?: number | null; // computed OE — NOT "ownerEarnings"
  baseOeFiscalYear?: number | null;
  netIncomeUsed?: number | null; // NOT "netIncome"
  daUsed?: number | null; // D&A — NOT "depreciation"
  capexUsed?: number | null; // sign-normalised negative — NOT "capex"
  wcChangeUsed?: number | null; // NOT "workingCapitalChange"
  // Forecast stream
  forecastOe: number[];
  pvOe: number[];
  discountFactors?: number[] | null;
  totalPvOe: number;        // NOT "pvForecastOe"
  // Terminal value
  terminalValue?: number | null;
  pvTerminalValue?: number | null; // NOT "pvTerminal"
  oeNPlus1?: number | null;
  // Equity bridge
  enterpriseValue?: number | null;
  netDebtUsed?: number | null;
  equityValue?: number | null;
  sharesOutstanding?: number | null;
  intrinsicValuePerShare?: number | null;
  // Market comparison (read-time)
  currentPrice?: number | null;
  upsideDownsidePct?: number | null;
}

export interface OwnerEarningsResponse {
  valuation: OwnerEarningsValuation;
  applicability: Applicability;
  dataQuality: DataQuality;
}

export interface OwnerEarningsHistoryEntry {
  runAt: string;
  baseOe?: number; // NOT "ownerEarnings"
  intrinsicValuePerShare?: number;
  oeGrowthRateUsed?: number; // NOT "growthRate"
  discountRateUsed?: number; // NOT "discountRate"
  enterpriseValue?: number;
  score?: number;
  category?: SuitabilityCategory;
}

export interface OwnerEarningsHistory {
  symbol: string;
  items: OwnerEarningsHistoryEntry[];
}

export interface OwnerEarningsState {
  loading: boolean;
  loadingHistory: boolean;
  error?: string;
  valuation?: OwnerEarningsValuation;
  applicability?: Applicability;
  dataQuality?: DataQuality;
  history?: OwnerEarningsHistory;
  freshness?: FreshnessInfo;
}

/* ====================================================================== */
/* RESIDUAL INCOME TYPES                                                   */
/* RI = BV/Share + Σ [ (ROE − CoE) × BV ] / (1 + CoE)^t + Terminal      */
/* ====================================================================== */

export interface ResidualIncomeValuation {
  symbol: string;
  companyId: number;
  currency: string;
  // Inputs used
  forecastYears: number;
  costOfEquityUsed: number;          // NOT "costOfEquity"
  betaUsed?: number | null;
  rfUsed?: number | null;
  erpUsed?: number | null;
  riGrowthRateUsed?: number | null;
  terminalGrowthRateUsed?: number | null;
  // Base values
  eps0?: number | null;   // NOT "eps"
  bvPerShare?: number | null;   // NOT "bookValuePerShare"
  roe0?: number | null;   // NOT "roe"
  ri0PerShare?: number | null;   // NOT "residualIncomePerShare"
  bvFiscalYear?: number | null;
  // Forecast stream
  forecastRiPerShare: number[];
  pvRiPerShare: number[];
  discountFactors?: number[] | null;
  totalPvRiPerShare: number;          // NOT "pvForecastRi"
  // Terminal value
  terminalRiPerShare?: number | null;
  terminalValueRi?: number | null;
  pvTerminalRiPerShare?: number | null;   // NOT "pvTerminal"
  // Intrinsic (equity-native — no EV bridge)
  intrinsicValuePerShare?: number | null;
  // Market comparison (read-time)
  currentPrice?: number | null;
  upsideDownsidePct?: number | null;
}

export interface ResidualIncomeResponse {
  valuation: ResidualIncomeValuation;
  applicability: Applicability;
  dataQuality: DataQuality;
}

export interface ResidualIncomeHistoryEntry {
  runAt: string;
  intrinsicValuePerShare?: number;
  roe0?: number;  // NOT "roe"
  costOfEquityUsed?: number;  // NOT "costOfEquity"
  ri0PerShare?: number;  // NOT "residualIncomePerShare"
  score?: number;
  category?: SuitabilityCategory;
}

export interface ResidualIncomeHistory {
  symbol: string;
  items: ResidualIncomeHistoryEntry[];
}

export interface ResidualIncomeState {
  loading: boolean;
  loadingHistory: boolean;
  error?: string;
  valuation?: ResidualIncomeValuation;
  applicability?: Applicability;
  dataQuality?: DataQuality;
  history?: ResidualIncomeHistory;
  freshness?: FreshnessInfo;
}

// ─────────────────────────────────────────────────────────────────────────────
// DIVIDEND ANALYSIS TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type DividendStatus = "stable" | "growing" | "declining" | "no_dividend";
export type DividendRating = "safe" | "moderate" | "borderline" | "risk" | "info";

export interface DividendSparkPoint {
  date: string;
  amount: number;
}

export interface DividendOverviewData {
  annual_dividend: number | null;
  per_period_amount: number | null;
  dividend_yield: number | null;
  payout_ratio_adj_eps: number | null;
  payout_ratio_gaap: number | null;
  payout_ratio_fcf: number | null;
  gaap_negative_eps: boolean;
  frequency: string;
  frequency_multiplier: number;
  ex_dividend_date: string | null;
  payment_date: string | null;
  last_increase_date: string | null;
  status: DividendStatus;
  sparkline: DividendSparkPoint[];
  current_price: number | null;
}

export interface DividendSafetyMetric {
  name: string;
  benchmark: string;
  value: number | null;
  formatted: string;
  rating: DividendRating;
  info_note?: string | null;
}

export interface DividendPolicy {
  growth_trend: string;
  cut_history: string;
  has_cut: boolean;
  cut_year: number | null;
  retention_rate: number | null;
}

export interface DividendSafetyData {
  composite_score: number;
  composite_category: SuitabilityCategory;
  metrics: DividendSafetyMetric[];
  earnings_stability: string;
  dividend_policy: DividendPolicy;
  strengths: string[];
  key_risks: string[];
}

export interface DividendGrowthChange {
  date: string;
  amount: number;
  change_pct: number;
  label: string;
  direction: "increase" | "decrease" | "flat";
}

export interface DividendGrowthData {
  growth_score: number;
  growth_category: SuitabilityCategory;
  cagr_1y: number | null;
  cagr_3y: number | null;
  cagr_5y: number | null;
  cagr_10y: number | null;
  consecutive_increases: number;
  annual_totals: Record<string, number>;
  recent_changes: DividendGrowthChange[];
}

export interface DividendYieldHistoryPoint {
  date: string;
  yield: number;
  price: number;
  ttm_dividend: number;
}

export interface DividendYieldData {
  current_yield: number | null;
  avg_yield_5y: number | null;
  yield_min_5y: number | null;
  yield_max_5y: number | null;
  yield_percentile_5y: number | null;
  yield_vs_sector: number | null;
  yield_vs_market: number | null;
  theory_signal: string | null;
  yield_history: DividendYieldHistoryPoint[];
}

export interface DividendAnalysis {
  symbol: string;
  pays_dividend: boolean;
  overview: DividendOverviewData | null;
  safety: DividendSafetyData | null;
  growth: DividendGrowthData | null;
  yield_analysis: DividendYieldData | null;
}

// ── Magic Formula ─────────────────────────────────────────────────────────────

export interface MFDiagnosticFlag {
  code: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  message: string;
  recommendation?: string | null;
  evidence?: Record<string, unknown> | null;
}

export interface MFInputs {
  ttm_ebit: number | null;
  ttm_ebit_source: string;
  ttm_quarters_used: number;
  enterprise_value: number | null;
  current_assets: number | null;
  cash_and_equivalents: number | null;
  current_liabilities: number | null;
  short_term_debt: number | null;
  ppe_net: number | null;
  goodwill_excluded: number | null;
  intangibles_excluded: number | null;
  fiscal_year_bs: number | null;
}

export interface MFValuation {
  earnings_yield: number | null;
  return_on_capital: number | null;
  net_working_capital: number | null;
  net_fixed_assets: number | null;
  invested_capital_mf: number | null;
  roic_from_ratios: number | null;
  roic_delta_note: string | null;
  earnings_yield_pct: number | null;
  return_on_capital_pct: number | null;
}

export interface MFIndustryContext {
  sector: string | null;
  industry: string | null;
  avg_ev_ebitda: number | null;
  implied_industry_earnings_yield: number | null;
  earnings_yield_vs_industry: "above" | "below" | "inline" | null;
  earnings_yield_premium_pct: number | null;
  avg_eps_growth: number | null;
  sample_size: number | null;
  calculation_date: string | null;
  context_note: string;
}

export interface MFApplicability {
  score: number;
  category: "Applicable" | "Caution" | "Not Applicable";
  excluded: boolean;
  exclusion_reason: string | null;
  flags: MFDiagnosticFlag[];
  suitability_summary: string | null;
}

export interface MFDataQuality {
  ttm_coverage: string;
  ev_source: string;
  bs_fiscal_year: number | null;
  days_since_bs_update: number | null;
  days_since_ev_snapshot: number | null;
  fallbacks_used: boolean;
  last_computed_at: string;
}

export interface MagicFormulaResponse {
  symbol: string;
  company_id: number;
  currency: string;
  inputs: MFInputs;
  valuation: MFValuation;
  industry_context: MFIndustryContext;
  applicability: MFApplicability;
  data_quality: MFDataQuality;
}

// ── CANSlim ───────────────────────────────────────────────────────────────────

export interface LetterEvidence {
  metrics: Record<string, unknown>;
  data_source: "database" | "live_fetch" | "unavailable";
  as_of_date: string | null;
}

export interface LetterScore {
  letter: string;
  name: string;
  score: number;
  weight: number;
  available: boolean;
  signal: "bullish" | "bearish" | "neutral" | "unavailable";
  headline: string;
  evidence: LetterEvidence;
  flags: string[];
}

export interface CANSlimLetters {
  C: LetterScore;
  A: LetterScore;
  N: LetterScore;
  S: LetterScore;
  L: LetterScore;
  I: LetterScore;
  M: LetterScore;
}

export interface CANSlimMarketCondition {
  condition:
  | "confirmed_uptrend"
  | "uptrend_pressure"
  | "distribution"
  | "downtrend"
  | "unknown";
  spy_price: number | null;
  spy_sma50: number | null;
  spy_sma200: number | null;
  sma50_vs_200: string;
  sma200_slope: string;
  description: string;
}

export interface CANSlimFlag {
  code: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  message: string;
  recommendation?: string | null;
}

export interface CANSlimDataQuality {
  letters_fully_scored: number;
  letters_unavailable: string[];
  benchmark_role: string;
  benchmark_symbol: string;
  confidence_adjustment: number;
  confidence_note: string | null;
  last_computed_at: string;
}

export interface CANSlimResponse {
  symbol: string;
  company_id: number;
  currency: string;
  letters: CANSlimLetters;
  composite_score: number;
  composite_category: "Strong" | "Moderate" | "Weak";
  market_condition: CANSlimMarketCondition;
  flags: CANSlimFlag[];
  data_quality: CANSlimDataQuality;
}

// ── Murphy Technical Analysis ──────────────────────────────────────────────────

export interface PriceLevel {
  price: number;
  level_type: "support" | "resistance";
  strength: "strong" | "moderate" | "weak";
  source: string;
  distance_pct: number;
}

export interface MACDReadings {
  macd_line: number | null;
  signal_line: number | null;
  histogram: number | null;
  histogram_prev: number | null;
  zero_line_position: "above" | "below";
  signal_cross: "bullish_cross" | "bearish_cross" | "none";
  zero_cross: "bullish_cross" | "bearish_cross" | "none";
  histogram_direction: string;
  divergence: "bullish" | "bearish" | "none" | "insufficient_data";
  divergence_note: string | null;
}

export interface RSIReadings {
  value: number | null;
  zone: "overbought" | "upper_neutral" | "lower_neutral" | "oversold";
  trend_context: string;
  divergence: "bullish" | "bearish" | "none" | "insufficient_data";
  divergence_note: string | null;
}

export interface TrendAnalysis {
  sma50: number | null;
  sma200: number | null;
  current_price: number;
  price_vs_sma50: "above" | "below" | "unknown";
  price_vs_sma200: "above" | "below" | "unknown";
  sma50_vs_sma200: "above" | "below" | "unknown";
  sma200_slope: "rising" | "falling" | "flat";
  sma50_slope: "rising" | "falling" | "flat";
  golden_cross: boolean;
  death_cross: boolean;
  cross_bars_ago: number | null;
  primary_trend: "uptrend" | "downtrend" | "sideways";
  intermediate_trend: "uptrend" | "downtrend" | "sideways";
  trend_strength: "strong" | "moderate" | "weak";
  distance_from_sma200_pct: number | null;
  distance_from_sma50_pct: number | null;
}

export interface VolumeAnalysis {
  obv_current: number | null;
  obv_trend: "rising" | "falling" | "flat";
  obv_confirms_price: boolean;
  vol_avg_10: number | null;
  vol_avg_50: number | null;
  vol_ratio: number | null;
  volume_signal: "accumulation" | "distribution" | "neutral";
  volume_signal_note: string;
}

export interface MomentumAnalysis {
  macd: MACDReadings;
  rsi: RSIReadings;
}

export interface BollingerReadings {
  upper: number | null;
  middle: number | null;
  lower: number | null;
  bandwidth: number | null;
  bandwidth_percentile: number | null;
  price_position: string;
  squeeze: boolean;
}

export interface StochasticReadings {
  k_line: number | null;
  d_line: number | null;
  zone: "overbought" | "neutral" | "oversold";
  signal: "bullish_cross" | "bearish_cross" | "none";
}

export interface OscillatorAnalysis {
  bollinger: BollingerReadings;
  stochastic: StochasticReadings;
}

export interface SupportResistanceAnalysis {
  levels: PriceLevel[];
  nearest_support: PriceLevel | null;
  nearest_resistance: PriceLevel | null;
  price_in_range: boolean;
  high_52w: number | null;
  low_52w: number | null;
  pct_from_52w_high: number | null;
  pct_from_52w_low: number | null;
}

export interface MurphySynthesis {
  overall_signal:
  | "strong_buy"
  | "buy"
  | "neutral"
  | "sell"
  | "strong_sell";
  signal_strength: number;
  risk_level: "low" | "moderate" | "high";
  dominant_factor: "trend" | "momentum" | "volume" | "oscillators";
  dominant_factor_note: string;
  key_observations: string[];
  conflicts: string[];
  caution_note: string | null;
}

export interface TechnicalDataQuality {
  bars_available: number;
  bars_required_200sma: number;
  bars_required_rsi: number;
  bars_required_macd: number;
  data_source: string;
  oldest_bar_date: string | null;
  newest_bar_date: string | null;
  sufficient_for_full_analysis: boolean;
  degraded_indicators: string[];
}

export interface MurphyAnalysisResponse {
  symbol: string;
  currency: string;
  as_of_date: string;
  current_price: number;
  data_quality: TechnicalDataQuality;
  trend: TrendAnalysis;
  momentum: MomentumAnalysis;
  volume: VolumeAnalysis;
  support_resistance: SupportResistanceAnalysis;
  oscillators: OscillatorAnalysis;
  synthesis: MurphySynthesis;
}

// ── Super Investors ─────────────────────────────────────────────────────────────

export interface SuperInvestorHolder {
  investor_name: string;
  firm: string;
  tag: string;
  style: string;
  shares: number;
  value: number;
  portfolio_weight: number;
  change_pct: number;
  change_type: "new" | "increased" | "decreased" | "held" | "sold";
  quarter_date: string;
}

export interface SuperInvestorRecentActivity {
  buyers: SuperInvestorHolder[];
  sellers: SuperInvestorHolder[];
}

export interface SuperInvestorData {
  ticker: string;
  holders: SuperInvestorHolder[];
  overlap_count: number;
  avg_portfolio_weight: number;
  conviction_level: "none" | "low" | "moderate" | "high" | "very_high";
  recent_activity: SuperInvestorRecentActivity;
}

export interface SuperInvestorHoldingPoint {
  quarter_date: string;
  shares_held: number;
  position_value: number;
  portfolio_weight: number;
  change_shares: number | null;
  change_pct: number | null;
  change_type: "new" | "increased" | "decreased" | "held" | "sold";
}

export interface SuperInvestorTimeline {
  investor_id: number;
  investor_name: string;
  firm: string;
  tag: string;
  style: string;
  holdings: SuperInvestorHoldingPoint[];
}

export interface SuperInvestorHistoryData {
  ticker: string;
  investors: SuperInvestorTimeline[];
  quarters: string[];
  earliest_date: string | null;
  latest_date: string | null;
  message?: string;
}

// ── Stock vs Index ─────────────────────────────────────────────────────────────
export interface StockVsIndexQuantitative {
  beta: number;
  alpha: number;
  stock_sharpe: number;
  index_sharpe: number;
  growth_score: number;
  revenue_cagr: number | null;
  eps_cagr: number | null;
  fcf_cagr: number | null;
  peg_ratio: number | null;
  score: number;
}

export interface StockVsIndexVisual {
  rs_trend: number;
  outperform_rate: number;
  stock_max_drawdown: number;
  index_max_drawdown: number;
  dd_ratio: number;
  score: number;
}

export interface StockVsIndexCharts {
  dates: string[];
  normalized_prices: Record<string, number[]>;
  relative_strength: Record<string, number[]>;
  rolling_12m_returns: Record<string, (number | null)[]>;
  drawdowns: Record<string, number[]>;
}

export interface StockVsIndexBenchmark {
  symbol: string;
  name: string;
}

export interface StockVsIndexResponse {
  symbol: string;
  primary_index: string;
  benchmarks: StockVsIndexBenchmark[];
  period_years: number;
  quantitative: StockVsIndexQuantitative;
  visual: StockVsIndexVisual;
  combined_score: number;
  recommendation: string;
  charts: StockVsIndexCharts;
}
// -- Moat Analysis -------------------------------------------------------------
// Economic moat durability assessment based on ROIC, margins, return stability,
// and capital efficiency.

export interface MoatDiagnosticFlag {
  code: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  message: string;
  recommendation?: string | null;
  evidence?: Record<string, unknown> | null;
}

export interface MoatInputs {
  nopat: number | null;
  invested_capital: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  net_margin: number | null;
  roic_5y_avg: number | null;
  roic_volatility: number | null;
  asset_turnover: number | null;
  fiscal_years_used: number;
  as_of_date: string | null;
  [k: string]: unknown;
}

export interface MoatValuation {
  roic: number | null;
  wacc: number | null;
  roic_minus_wacc: number | null;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
  net_margin_pct: number | null;
  roic_5y_avg: number | null;
  roic_5y_std: number | null;
  roic_stability_score: number | null;
  asset_turnover: number | null;
  capital_efficiency_score: number | null;
  moat_score: number | null;
  moat_category: "Wide" | "Narrow" | "None" | "Unknown";
  moat_summary: string | null;
}

export interface MoatIndustryContext {
  sector: string | null;
  industry: string | null;
  avg_roic: number | null;
  roic_vs_industry: "above" | "below" | "inline" | null;
  avg_margin: number | null;
  sample_size: number | null;
  context_note: string;
}

export interface MoatApplicability {
  score: number;
  category: "Applicable" | "Caution" | "Not Applicable";
  excluded: boolean;
  exclusion_reason: string | null;
  flags: MoatDiagnosticFlag[];
  suitability_summary: string | null;
}

export interface MoatDataQuality {
  data_sources: string;
  fiscal_year_end: number | null;
  quarters_used: number;
  days_since_update: number | null;
  fallbacks_used: boolean;
  last_computed_at: string;
}

export interface MoatResponse {
  symbol: string;
  company_id: number;
  currency: string;
  inputs: MoatInputs;
  valuation: MoatValuation;
  industry_context: MoatIndustryContext;
  applicability: MoatApplicability;
  data_quality: MoatDataQuality;
}

// ── Risk Assessment Types ──

export type RiskCategory =
  | "Very Low Downside"
  | "Moderate"
  | "Elevated"
  | "High Risk";

export type RiskSeverity = "low" | "moderate" | "elevated" | "high" | "severe";

export type LayerName =
  | "business_fragility"
  | "balance_sheet"
  | "valuation_compression"
  | "earnings_stress"
  | "drawdown_risk";

export interface RiskMetric {
  name: string;
  value?: number | null;
  label: string;
  status: "pass" | "caution" | "fail" | "na";
  weight: number;
  evidence?: Record<string, unknown> | null;
  threshold_description?: string | null;
}

export interface RiskLayer {
  name: LayerName;
  display_name: string;
  score: number;
  category: RiskSeverity;
  metrics: RiskMetric[];
  weight: number;
}

export interface BusinessFragility extends RiskLayer {
  moat_score?: number | null;
  moat_category?: string | null;
  roic_minus_wacc?: number | null;
  sector?: string | null;
  industry?: string | null;
  recurrence_classification?: string | null;
  pricing_power_assessment?: string | null;
}

export interface BalanceSheetRisk extends RiskLayer {
  debt_to_ebitda?: number | null;
  net_debt_to_ebitda?: number | null;
  interest_coverage?: number | null;
  current_ratio?: number | null;
  quick_ratio?: number | null;
  debt_to_equity?: number | null;
  fcf_conversion?: number | null;
  fcf_stability_pct?: number | null;
}

export interface ValuationCompressionRisk extends RiskLayer {
  pe_current?: number | null;
  pe_percentile?: number | null;
  pe_5y_min?: number | null;
  pe_5y_max?: number | null;
  pe_5y_median?: number | null;
  ev_ebitda_current?: number | null;
  ev_ebitda_percentile?: number | null;
  peg_ratio?: number | null;
}

export interface EarningsStressRisk extends RiskLayer {
  eps_cagr_3y?: number | null;
  eps_cagr_5y?: number | null;
  revenue_cagr_3y?: number | null;
  revenue_cagr_5y?: number | null;
  net_margin_current?: number | null;
  operating_margin_trend?: "expanding" | "stable" | "contracting" | null;
  revenue_eps_alignment?: "aligned" | "diverging" | "volatile" | null;
  eps_volatility?: number | null;
}

export interface DrawdownRisk extends RiskLayer {
  max_drawdown_1y?: number | null;
  max_drawdown_3y?: number | null;
  max_drawdown_5y?: number | null;
  beta_5y?: number | null;
  current_drawdown?: number | null;
  crisis_drawdowns?: CrisisDrawdown[] | null;
  recovery_time_days?: number | null;
}

export interface CrisisDrawdown {
  crisis_name: string;
  start_date: string;
  end_date: string;
  max_drawdown: number;
  start_value: number;
  end_value: number;
}

export interface ScenarioResult {
  scenario: string;
  probability: number;
  eps_growth: number;
  exit_pe: number;
  future_eps: number;
  future_value: number;
  total_return: number;
  downside: number;
}

export interface BearCase {
  eps_growth_assumption: number;
  exit_pe_ratio: number;
  future_value: number;
  current_price: number;
  downside_pct: number;
}

export interface CompositeScore {
  score: number;
  category: RiskCategory;
  maximum_expected_loss_pct: number | null;
  bear_case: BearCase;
}

export interface RiskDataQuality {
  data_sources: string;
  fiscal_year_end?: number | null;
  days_since_update?: number | null;
  fallbacks_used: boolean;
  last_computed_at: string;
}

export interface RiskAiNarrative {
  narrative: string;
  model: string;
  generated_at: string;
  generation_time_ms?: number | null;
}

export interface RiskAssessmentResponse {
  symbol: string;
  company_id: number;
  currency: string;
  composite: CompositeScore;
  layers: Record<LayerName, RiskLayer>;
  scenarios?: ScenarioResult[] | null;
  ai_narrative?: RiskAiNarrative | null;
  data_quality: RiskDataQuality;
}