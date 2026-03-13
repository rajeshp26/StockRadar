// web/src/features/analysis/valuation/methods.ts
// CHANGE: ownerEarnings and residualIncome enabled: true (were false)
export type ValuationMethodId =
  | "rule1"
  | "dcf"
  | "ddm"
  | "ownerEarnings"
  | "residualIncome";

export interface ValuationMethodConfig {
  id:          ValuationMethodId;
  label:       string;
  shortLabel:  string;
  description: string;
  enabled:     boolean;
}

export const VALUATION_METHODS: ValuationMethodConfig[] = [
  {
    id:          "rule1",
    label:       "Rule #1 (Phil Town)",
    shortLabel:  "Rule #1",
    description: "Earnings growth & multiple based intrinsic value",
    enabled:     true,
  },
  {
    id:          "ddm",
    label:       "Dividend Discount Model",
    shortLabel:  "DDM",
    description: "Dividend yield & growth based valuation",
    enabled:     true,
  },
  {
    id:          "dcf",
    label:       "Discounted Cash Flow",
    shortLabel:  "DCF",
    description: "Cash‑flow based intrinsic value",
    enabled:     true, // ← was false; DCF panel already ships
  },
  {
    id:          "ownerEarnings",
    label:       "Owner Earnings",
    shortLabel:  "OE",
    description: "Buffett owner earnings valuation",
    enabled:     true, // ← NEW
  },
  {
    id:          "residualIncome",
    label:       "Residual Income",
    shortLabel:  "RI",
    description: "Economic profit based valuation",
    enabled:     true, // ← NEW
  },
];