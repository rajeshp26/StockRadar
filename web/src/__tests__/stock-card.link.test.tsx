import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StockCard } from "@/components/dashboard/stock-card";

vi.mock("@/hooks/usePriceData", () => ({
  usePriceData: () => ({
    price: 150.25,
    change: 2.5,
    changePercent: 1.68,
    lastUpdated: new Date().toISOString(),
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, prefetch, ...props }: any) => (
    <a href={href} data-prefetch={String(prefetch)} {...props}>
      {children}
    </a>
  ),
}));

const mockStock = {
  id: 1,
  symbol: "AAPL",
  name: "Apple Inc.",
  targetBuy: 140,
  targetSell: 200,
};

describe("StockCard — Link Prefetch", () => {
  it("renders as an <a> element with correct href", () => {
    render(
      <StockCard
        stock={mockStock as any}
        onRemove={() => {}}
        onEdit={() => {}}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/analysis/AAPL");
  });

  it("has prefetch attribute set to true", () => {
    render(
      <StockCard
        stock={mockStock as any}
        onRemove={() => {}}
        onEdit={() => {}}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("data-prefetch", "true");
  });

  it("displays the stock symbol", () => {
    render(
      <StockCard
        stock={mockStock as any}
        onRemove={() => {}}
        onEdit={() => {}}
      />,
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("displays the stock price", () => {
    render(
      <StockCard
        stock={mockStock as any}
        onRemove={() => {}}
        onEdit={() => {}}
      />,
    );
    expect(screen.getByText("$150.25")).toBeInTheDocument();
  });
});
