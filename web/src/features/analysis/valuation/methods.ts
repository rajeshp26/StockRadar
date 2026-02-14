export type ValuationMethodId =
  | "rule1"
  | "dcf"
  | "ddm"
  | "ownerEarnings"
  | "residualIncome";

export interface ValuationMethodConfig {
  id: ValuationMethodId;
  label: string;
  shortLabel: string;
  description: string;
  enabled: boolean;
}

export const VALUATION_METHODS: ValuationMethodConfig[] = [
  {
    id: "rule1",
    label: "Rule #1 (Phil Town)",
    shortLabel: "Rule #1",
    description: "Earnings growth & multiple based intrinsic value",
    enabled: true,
  },
  {
    id: "dcf",
    label: "Discounted Cash Flow",
    shortLabel: "DCF",
    description: "Cash‑flow based intrinsic value",
    enabled: false, // enable later
  },
  {
    id: "ddm",
    label: "Dividend Discount Model",
    shortLabel: "DDM",
    description: "Dividend yield & growth based valuation",
    enabled: false,
  },
  {
    id: "ownerEarnings",
    label: "Owner Earnings",
    shortLabel: "OE",
    description: "Buffett owner earnings valuation",
    enabled: false,
  },
  {
    id: "residualIncome",
    label: "Residual Income",
    shortLabel: "RI",
    description: "Economic profit based valuation",
    enabled: false,
  },
];