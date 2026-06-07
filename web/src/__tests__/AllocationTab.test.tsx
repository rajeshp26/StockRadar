import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const mockUsePortfolioAllocation = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    usePortfolioAllocation: (...args: any[]) => mockUsePortfolioAllocation(...args),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

import { AllocationTab } from "@/features/portfolio/components/AllocationTab";

function makeFlatSegments() {
    return {
        success: true,
        group_by: "sector",
        segments: [
            { segment: "Technology", value: 50000, weight: 62.5, count: 2, gain_loss: 10000 },
            { segment: "Energy", value: 30000, weight: 37.5, count: 1, gain_loss: -2000 },
        ],
        types: [],
        total_value: 80000,
    };
}

function makeHierarchicalData() {
    return {
        success: true,
        group_by: "sector",
        segments: [],
        types: [
            {
                type: "stock",
                type_label: "Stocks",
                value: 80000,
                weight: 80.0,
                count: 3,
                gain_loss: 5500,
                sectors: [
                    { segment: "Technology", value: 50000, weight: 62.5, count: 2, gain_loss: 10000 },
                    { segment: "Energy", value: 30000, weight: 37.5, count: 1, gain_loss: -2000 },
                ],
            },
            {
                type: "etf",
                type_label: "ETFs",
                value: 20000,
                weight: 20.0,
                count: 2,
                gain_loss: 1000,
                sectors: [
                    { segment: "Unknown", value: 20000, weight: 100.0, count: 2, gain_loss: 1000 },
                ],
            },
        ],
        total_value: 100000,
    };
}

describe("AllocationTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUsePortfolioAllocation.mockReturnValue({ data: makeHierarchicalData(), isLoading: false });
    });

    it("renders all group-by toggle buttons", () => {
        render(<AllocationTab />);
        expect(screen.getByText("Sector")).toBeInTheDocument();
        expect(screen.getByText("Geography")).toBeInTheDocument();
        expect(screen.getByText("Account Type")).toBeInTheDocument();
    });

    it("default group-by 'Sector' is highlighted as active", () => {
        const { container } = render(<AllocationTab />);
        const activeBtn = container.querySelector("button.bg-blue-600");
        expect(activeBtn).toBeTruthy();
        expect(activeBtn?.textContent).toContain("Sector");
    });

    it("switches group-by on button click", () => {
        render(<AllocationTab />);
        fireEvent.click(screen.getByText("Geography"));
        const geoBtn = screen.getByText("Geography");
        expect(geoBtn.className).toContain("bg-blue-600");
    });

    it("renders hierarchical type labels", () => {
        render(<AllocationTab />);
        expect(screen.getByText("Stocks")).toBeInTheDocument();
        expect(screen.getByText("ETFs")).toBeInTheDocument();
    });

    it("renders sector names inside type groups", () => {
        render(<AllocationTab />);
        expect(screen.getByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Energy")).toBeInTheDocument();
    });

    it("shows count in parentheses for types", () => {
        render(<AllocationTab />);
        expect(screen.getByText("(3)")).toBeInTheDocument();
        const countTwos = screen.getAllByText("(2)");
        expect(countTwos.length).toBeGreaterThanOrEqual(1);
    });

    it("shows positive gain_loss in green and negative in red", () => {
        render(<AllocationTab />);
        const posGain = screen.getByText("+$10,000.00");
        expect(posGain.className).toContain("text-green-400");
        const negGain = screen.getByText(($) => $.includes("2,000") && $.includes("-"));
        expect(negGain.className).toContain("text-red-400");
    });

    it("renders flat segments when no hierarchical data (geography/account)", () => {
        mockUsePortfolioAllocation.mockReturnValue({ data: makeFlatSegments(), isLoading: false });
        render(<AllocationTab />);
        expect(screen.getByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Energy")).toBeInTheDocument();
    });

    it("shows loading skeletons while fetching", () => {
        mockUsePortfolioAllocation.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<AllocationTab />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no data", () => {
        mockUsePortfolioAllocation.mockReturnValue({
            data: { success: true, group_by: "sector", segments: [], types: [], total_value: 0 },
            isLoading: false,
        });
        render(<AllocationTab />);
        expect(screen.getByText("No allocation data available")).toBeInTheDocument();
    });

    it("renders with account filter", () => {
        render(<AllocationTab accountIds={[1]} />);
        expect(screen.getByText("Stocks")).toBeInTheDocument();
    });
});
