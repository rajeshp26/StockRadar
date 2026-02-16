import type { MethodPanelProps } from "./method-panel";
import { DcfSummary } from "./dcf-summary";
import { DcfHow } from "./dcf-how";
import { DcfSuitability } from "./dcf-suitability";
import { DcfHistory } from "./dcf-history";

export function getDcfMethodProps(symbol: string): MethodPanelProps {
  return {
    summary: <DcfSummary symbol={symbol} />,
    how: <DcfHow symbol={symbol} />,
    suitability: <DcfSuitability symbol={symbol} />,
    history: <DcfHistory symbol={symbol} />,
  };
}
``