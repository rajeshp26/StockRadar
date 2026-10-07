import { describe, it, expect } from "vitest";
import { formatAxisNumber } from "@/lib/compact-number";

describe("formatAxisNumber (Y-axis compact tick labels)", () => {
    it("under 1,000: returns the integer value", () => {
        expect(formatAxisNumber(0)).toBe("0");
        expect(formatAxisNumber(500)).toBe("500");
        expect(formatAxisNumber(977)).toBe("977");
        expect(formatAxisNumber(999)).toBe("999");
    });

    it("thousands: single-decimal k, trailing .0 stripped", () => {
        expect(formatAxisNumber(1_000)).toBe("1k");
        expect(formatAxisNumber(1_234)).toBe("1.2k");
        expect(formatAxisNumber(9_999)).toBe("10k");
        expect(formatAxisNumber(20_000)).toBe("20k");
        expect(formatAxisNumber(100_000)).toBe("100k");
        expect(formatAxisNumber(197_667)).toBe("197.7k");
        expect(formatAxisNumber(258_426)).toBe("258.4k");
    });

    it("millions: M tier (the previous '1500.0k' defect)", () => {
        expect(formatAxisNumber(1_000_000)).toBe("1M");
        expect(formatAxisNumber(1_234_567)).toBe("1.2M");
        expect(formatAxisNumber(1_500_000)).toBe("1.5M");
        expect(formatAxisNumber(12_000_000)).toBe("12M");
    });

    it("billions: B tier", () => {
        expect(formatAxisNumber(1_000_000_000)).toBe("1B");
        expect(formatAxisNumber(2_500_000_000)).toBe("2.5B");
    });

    it("negative values format symmetrically", () => {
        expect(formatAxisNumber(-500)).toBe("-500");
        expect(formatAxisNumber(-1_500)).toBe("-1.5k");
        expect(formatAxisNumber(-1_000_000)).toBe("-1M");
    });
});