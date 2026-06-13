import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PERatioGauge, type PERatioGaugeProps } from "@/features/analysis/components/pe-ratio-gauge";

function renderGauge(props: Partial<PERatioGaugeProps> = {}) {
  const defaults: PERatioGaugeProps = {
    current: 18.4,
    min: 9.2,
    max: 42.1,
    avg: 21.3,
  };
  return render(<PERatioGauge {...defaults} {...props} />);
}

describe("PERatioGauge", () => {
  it("renders SVG with correct aria-label", () => {
    renderGauge({ current: 18.4 });
    const svg = screen.getByLabelText("P/E Ratio Gauge: 18.4");
    expect(svg).toBeInTheDocument();
    expect(svg.tagName).toBe("svg");
  });

  it("renders central P/E value (in SVG text and stat pill) and label inside SVG", () => {
    renderGauge({ current: 18.4 });
    const matches = screen.getAllByText("18.4");
    expect(matches.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("P/E Ratio")).toBeInTheDocument();
  });

  it("renders all four stat pills", () => {
    renderGauge({ current: 18.4, min: 9.2, max: 42.1, avg: 21.3 });
    expect(screen.getByText("Min")).toBeInTheDocument();
    expect(screen.getByText("Avg")).toBeInTheDocument();
    expect(screen.getByText("Max")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
  });

  it("renders stat pill values correctly", () => {
    renderGauge({ current: 18.4, min: 9.2, max: 42.1, avg: 21.3 });
    expect(screen.getByText("9.2")).toBeInTheDocument();
    expect(screen.getByText("21.3")).toBeInTheDocument();
    expect(screen.getByText("42.1")).toBeInTheDocument();
    const currentTexts = screen.getAllByText("18.4");
    expect(currentTexts.length).toBeGreaterThanOrEqual(1);
  });

  describe("valuation badge", () => {
    it("shows Fairly valued when current is within 85%-125% of avg", () => {
      renderGauge({ current: 21.3, avg: 21.3 });
      expect(screen.getByText("Fairly valued")).toBeInTheDocument();
    });

    it("shows Fairly valued when current is near avg", () => {
      renderGauge({ current: 20.0, avg: 21.3 });
      expect(screen.getByText("Fairly valued")).toBeInTheDocument();
    });

    it("shows Undervalued when current < avg * 0.85", () => {
      renderGauge({ current: 10.0, avg: 21.3 });
      expect(screen.getByText("Undervalued")).toBeInTheDocument();
    });

    it("shows Overvalued when current > avg * 1.25", () => {
      renderGauge({ current: 30.0, avg: 21.3 });
      expect(screen.getByText("Overvalued")).toBeInTheDocument();
    });
  });

  describe("edge cases", () => {
    it("handles current value below min by clamping", () => {
      renderGauge({ current: 5.0, min: 9.2, max: 42.1, avg: 21.3 });
      const matches = screen.getAllByText("5.0");
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Undervalued")).toBeInTheDocument();
    });

    it("handles current value above max by clamping", () => {
      renderGauge({ current: 50.0, min: 9.2, max: 42.1, avg: 21.3 });
      const matches = screen.getAllByText("50.0");
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Overvalued")).toBeInTheDocument();
    });

    it("handles min === max (single value)", () => {
      renderGauge({ current: 15.0, min: 15.0, max: 15.0, avg: 15.0 });
      const matches = screen.getAllByText("15.0");
      expect(matches.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Fairly valued")).toBeInTheDocument();
    });
  });
});
