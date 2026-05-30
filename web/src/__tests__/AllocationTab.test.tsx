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

function makeSegments() {
    return {
        success: true,
        group_by: "sector",
        segments: [
            { segment: "Technology", value: 50000, weight: 62.5, count: 2, gain_loss: 10000 },
            { segment: "Energy", value: 30000, weight: 37.5, count: 1, gain_loss: -2000 },
        ],
        total_value: 80000,
    };
}

describe("AllocationTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUsePortfolioAllocation.mockReturnValue({ data: makeSegments(), isLoading: false });
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

    it("renders allocation segments with values and weights", () => {
        render(<AllocationTab />);
        expect(screen.getByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Energy")).toBeInTheDocument();
        expect(screen.getByText("62.5%")).toBeInTheDocument();
        expect(screen.getByText("37.5%")).toBeInTheDocument();
        expect(screen.getByText("$50,000.00")).toBeInTheDocument();
        expect(screen.getByText("$30,000.00")).toBeInTheDocument();
    });

    it("shows positive gain_loss in green and negative in red", () => {
        render(<AllocationTab />);
        const posGain = screen.getByText("+$10,000.00");
        expect(posGain.className).toContain("text-green-400");
        const negGain = screen.getByText(($) => $.includes("$") && $.includes("-2,000"));
        expect(negGain.className).toContain("text-red-400");
    });

    it("shows segment count in parentheses", () => {
        render(<AllocationTab />);
        expect(screen.getByText("(2)")).toBeInTheDocument();
        expect(screen.getByText("(1)")).toBeInTheDocument();
    });

    it("shows loading skeletons while fetching", () => {
        mockUsePortfolioAllocation.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<AllocationTab />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no segments", () => {
        mockUsePortfolioAllocation.mockReturnValue({
            data: { success: true, group_by: "sector", segments: [], total_value: 0 },
            isLoading: false,
        });
        render(<AllocationTab />);
        expect(screen.getByText("No allocation data available")).toBeInTheDocument();
    });

    it("renders with account filter", () => {
        render(<AllocationTab accountIds={[1]} />);
        expect(screen.getByText("Sector")).toBeInTheDocument();
    });
});
