import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, act, screen, waitFor } from "@testing-library/react";
import React from "react";

const mockUseHoldingExists = vi.fn().mockReturnValue({ data: { held: false } });

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
  useHoldingExists: (...args: unknown[]) => mockUseHoldingExists(...args),
}));

vi.mock("@/features/analysis/hooks/usePredictiveTabPrefetch", () => ({
  usePredictiveTabPrefetch: vi.fn(),
}));

vi.mock("@/features/analysis/utils/prefetch-valuations", () => ({
  prefetchAllValuations: vi.fn(),
}));

vi.mock("@/features/analysis/hooks/useLivePrice", () => ({
  useLivePrice: vi.fn().mockReturnValue({ price: 150, change: 1, changePercent: 0.5, lastUpdated: null, loading: false, error: null }),
}));

vi.mock("@/lib/time", () => ({ formatTimestamp: vi.fn().mockReturnValue("now") }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ back: vi.fn() }), useParams: () => ({ symbol: "AAPL" }) }));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return { ...(actual as object), useQuery: vi.fn().mockReturnValue({ data: null, isPending: false, error: null }), useQueryClient: vi.fn().mockReturnValue({ prefetchQuery: vi.fn() }) };
});

vi.mock("@/features/analysis/components/method-selector", () => ({
  MethodSelector: ({ method, onChange }: { method: string; onChange: (m: string) => void }) =>
    React.createElement("div", { "data-testid": "method-selector" },
      React.createElement("select", { value: method, onChange: (e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value), "data-testid": "method-select" },
        React.createElement("option", { value: "overview" }, "Overview"),
        React.createElement("option", { value: "dcf" }, "DCF"),
        React.createElement("option", { value: "rule1" }, "Rule 1"),
      ),
    ),
}));

vi.mock("@/features/analysis/components/dcf-panel", () => ({
  DcfPanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "dcf-panel" }, `DCF ${symbol}`),
}));

vi.mock("@/features/analysis/components/intrinsic-panel", () => ({
  IntrinsicPanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "intrinsic-panel" }, `Intrinsic ${symbol}`),
}));

import { ClientTabs } from "@/components/analysis/client-tabs";

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("Analysis Page — Race Conditions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("P3-UT-27: rapid method switching does not cause errors", async () => {
    render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    const select = screen.getByTestId("method-select");

    await act(async () => {
      fireEvent.change(select, { target: { value: "dcf" } });
      fireEvent.change(select, { target: { value: "rule1" } });
      fireEvent.change(select, { target: { value: "overview" } });
      await tick();
    });

    expect(screen.getByTestId("method-selector")).toBeInTheDocument();
  });

  it("P3-UT-28: rapid tab switching does not cause errors", async () => {
    const { container } = render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    const tabButtons = () => container.querySelectorAll(".glass-segmented-item");

    await act(async () => {
      const btns = tabButtons();
      if (btns[1]) fireEvent.click(btns[1]);
      await tick();
      const btns2 = tabButtons();
      if (btns2[2]) fireEvent.click(btns2[2]);
      await tick();
      const btns3 = tabButtons();
      if (btns3[0]) fireEvent.click(btns3[0]);
      await tick();
    });

    const activeBtn = container.querySelector(".glass-segmented-item.active");
    expect(activeBtn).toBeTruthy();
  });

  it("P3-UT-29: tab switch then immediate method switch works", async () => {
    const { container } = render(React.createElement(ClientTabs, { symbol: "AAPL" }));

    await act(async () => {
      const btns1 = container.querySelectorAll(".glass-segmented-item");
      if (btns1[1]) fireEvent.click(btns1[1]);
      await tick();
      const btns2 = container.querySelectorAll(".glass-segmented-item");
      if (btns2[0]) fireEvent.click(btns2[0]);
      await tick();
    });

    await act(async () => {
      const select = screen.getByTestId("method-select");
      fireEvent.change(select, { target: { value: "dcf" } });
      await tick();
    });

    expect(screen.getByTestId("method-selector")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("dcf-panel")).toBeInTheDocument();
    });
  });

  it("P3-UT-30: state remains consistent during fast interactions", async () => {
    const { container } = render(React.createElement(ClientTabs, { symbol: "AAPL" }));

    await act(async () => {
      const tabButtons = document.querySelectorAll(".glass-segmented-item");
      for (let i = 0; i < 5; i++) {
        const btn = tabButtons[i % tabButtons.length];
        if (btn) fireEvent.click(btn);
      }
      await tick();
    });

    const intrinsicBtn = container.querySelector(".glass-segmented-item");
    if (intrinsicBtn) {
      await act(async () => {
        fireEvent.click(intrinsicBtn);
        await tick();
      });
    }

    await act(async () => {
      const select = screen.getByTestId("method-select");
      for (let i = 0; i < 5; i++) {
        fireEvent.change(select, { target: { value: i % 2 === 0 ? "dcf" : "rule1" } });
      }
      await tick();
    });

    await waitFor(() => {
      expect(screen.getByTestId("method-selector")).toBeInTheDocument();
    });
  });
});
