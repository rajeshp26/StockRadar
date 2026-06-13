import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ValuationGauge, type ValuationGaugeProps } from "@/features/analysis/components/valuation-gauge";
import type { GaugeConfig } from "@/features/analysis/types/analysis.types";

function makeConfig(overrides: Partial<GaugeConfig> = {}): GaugeConfig {
  return {
    display_mode: "gauge",
    benchmark: "sector",
    benchmark_value: 20.0,
    band_low: 15.0,
    band_high: 25.0,
    current_value: 18.4,
    current_quarter_raw: null,
    min_value: 9.2,
    max_value: 42.1,
    avg_value: 21.3,
    positive_count: 40,
    total_quarters: 52,
    na_count: 0,
    warnings: [],
    ...overrides,
  };
}

function renderGauge(config: GaugeConfig, props: Partial<ValuationGaugeProps> = {}) {
  return render(
    <ValuationGauge
      config={config}
      unit="x"
      label="P/E Ratio"
      metricId="pe"
      {...props}
    />,
  );
}

describe("ValuationGauge", () => {
  describe("gauge mode", () => {
    it("renders SVG with correct aria-label", () => {
      renderGauge(makeConfig({ current_value: 18.4 }));
      const svg = screen.getByLabelText("P/E Ratio Gauge: 18.4");
      expect(svg).toBeInTheDocument();
      expect(svg.tagName).toBe("svg");
    });

    it("renders central value and label inside SVG", () => {
      renderGauge(makeConfig({ current_value: 18.4 }));
      const matches = screen.getAllByText("18.4");
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("P/E Ratio")).toBeInTheDocument();
    });

    it("renders all four stat pills", () => {
      renderGauge(makeConfig());
      expect(screen.getByText("Min")).toBeInTheDocument();
      expect(screen.getByText("Avg")).toBeInTheDocument();
      expect(screen.getByText("Max")).toBeInTheDocument();
      expect(screen.getByText("Current")).toBeInTheDocument();
    });

    it("renders stat pill values", () => {
      renderGauge(makeConfig());
      expect(screen.getByText("9.2")).toBeInTheDocument();
      expect(screen.getByText("21.3")).toBeInTheDocument();
      expect(screen.getByText("42.1")).toBeInTheDocument();
      expect(screen.getAllByText("18.4").length).toBeGreaterThanOrEqual(1);
    });

    it("shows Fairly valued when current is within band", () => {
      renderGauge(makeConfig({ current_value: 20.0, band_low: 15.0, band_high: 25.0, avg_value: 21.3 }));
      expect(screen.getByText("Fairly valued")).toBeInTheDocument();
    });

    it("shows Undervalued when current is below band_low", () => {
      renderGauge(makeConfig({ current_value: 10.0, band_low: 15.0, band_high: 25.0, avg_value: 21.3 }));
      expect(screen.getByText("Undervalued")).toBeInTheDocument();
    });

    it("shows Overvalued when current is above band_high", () => {
      renderGauge(makeConfig({ current_value: 30.0, band_low: 15.0, band_high: 25.0, avg_value: 21.3 }));
      expect(screen.getByText("Overvalued")).toBeInTheDocument();
    });

    it("falls back to fallback text when critical values are null", () => {
      renderGauge(makeConfig({ current_value: null, min_value: null, max_value: null, avg_value: null }));
      expect(screen.getByText("Insufficient data for gauge display")).toBeInTheDocument();
    });
  });

  describe("compact_gauge mode", () => {
    it("renders SVG without stat pills", () => {
      renderGauge(makeConfig({ display_mode: "compact_gauge", current_value: 18.4 }));
      const svg = screen.getByLabelText("P/E Ratio Gauge: 18.4");
      expect(svg).toBeInTheDocument();
      expect(screen.queryByText("Min")).not.toBeInTheDocument();
      expect(screen.queryByText("Avg")).not.toBeInTheDocument();
      expect(screen.queryByText("Max")).not.toBeInTheDocument();
      expect(screen.queryByText("Current")).not.toBeInTheDocument();
    });

    it("renders valuation badge in compact mode", () => {
      renderGauge(makeConfig({ display_mode: "compact_gauge", current_value: 18.4 }));
      expect(screen.getByText("Fairly valued")).toBeInTheDocument();
    });
  });

  describe("slider mode", () => {
    it("renders slider with min and max values", () => {
      renderGauge(makeConfig({ display_mode: "slider" }));
      expect(screen.getByText("9.2×")).toBeInTheDocument();
      expect(screen.getByText("42.1×")).toBeInTheDocument();
    });

    it("shows avg marker on slider", () => {
      renderGauge(makeConfig({ display_mode: "slider" }));
      expect(screen.getByText(/avg /)).toBeInTheDocument();
    });

    it("shows N/A count when na_count > 0", () => {
      renderGauge(makeConfig({ display_mode: "slider", na_count: 3, total_quarters: 52 }));
      expect(screen.getByText("3/52 N/A")).toBeInTheDocument();
    });

    it("shows warning when all values are null and na_count > 0", () => {
      renderGauge(makeConfig({
        display_mode: "slider",
        min_value: null,
        max_value: null,
        avg_value: null,
        na_count: 4,
        total_quarters: 12,
      }));
      expect(screen.getByText("All quarters have negative earnings — not meaningful")).toBeInTheDocument();
    });
  });

  describe("disabled mode", () => {
    it("shows warning message", () => {
      renderGauge(makeConfig({
        display_mode: "disabled",
        warnings: ["Not applicable for Financial Services"],
      }));
      expect(screen.getByText("Not applicable for Financial Services")).toBeInTheDocument();
    });
  });

  describe("edge cases", () => {
    it("handles current value below min with outside indicator", () => {
      renderGauge(makeConfig({
        display_mode: "slider",
        current_value: 5.0,
        min_value: 9.2,
        max_value: 42.1,
        avg_value: 21.3,
      }));
      expect(screen.getByText(/outside positive range/)).toBeInTheDocument();
    });

    it("handles current value above max with outside indicator", () => {
      renderGauge(makeConfig({
        display_mode: "slider",
        current_value: 50.0,
        min_value: 9.2,
        max_value: 42.1,
        avg_value: 21.3,
      }));
      expect(screen.getByText(/outside positive range/)).toBeInTheDocument();
    });

    it("handles min equals max", () => {
      renderGauge(makeConfig({ min_value: 15.0, max_value: 15.0, avg_value: 15.0, current_value: 15.0 }));
      const svg = screen.getByLabelText("P/E Ratio Gauge: 15.0");
      expect(svg).toBeInTheDocument();
    });
  });
});
