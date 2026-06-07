import { describe, it, expect, vi } from "vitest";
import { QK } from "@/lib/query-keys";

describe("Query keys", () => {
    it("holdingExists key includes uppercased symbol", () => {
        expect(QK.holdingExists("aapl")).toEqual(["portfolio", "holding", "exists", "AAPL"]);
    });

    it("holdingPerformance key changes with period", () => {
        const key1M = QK.holdingPerformance("AAPL", "1M");
        const key1Y = QK.holdingPerformance("AAPL", "1Y");
        expect(key1M).not.toEqual(key1Y);
    });

    it("holdingDividends key includes uppercased symbol", () => {
        expect(QK.holdingDividends("msft")).toEqual(["portfolio", "holding", "dividends", "MSFT"]);
    });
});
