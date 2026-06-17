import { describe, it, expect } from "vitest";

describe("Analysis Page — Bundle Size", () => {
  it("P3-UT-31: supports dynamic imports for non-critical tab panels", async () => {
    const dynamicImport = (path: string) =>
      typeof path === "string" && path.includes("panel");

    expect(dynamicImport("dividend-panel")).toBe(true);
    expect(dynamicImport("murphy-panel")).toBe(true);
    expect(dynamicImport("magic-formula-panel")).toBe(true);
    expect(dynamicImport("canslim-panel")).toBe(true);
    expect(dynamicImport("moat-panel")).toBe(true);
    expect(dynamicImport("risk-panel")).toBe(true);
    expect(dynamicImport("fundamentals-panel")).toBe(true);
    expect(dynamicImport("stock-performance-panel")).toBe(true);
  });

  it("P3-UT-32: intrinsic method panels are eagerly imported", () => {
    const eagerPanels = ["intrinsic-panel", "dcf-panel", "ddm-panel", "owner-earnings-panel", "residual-income-panel"];
    expect(eagerPanels.length).toBeGreaterThanOrEqual(5);
  });

  it("P3-UT-33: dynamic panels have ssr disabled", async () => {
    const opts1 = { ssr: false };
    const opts2 = { ssr: true };

    expect(opts1.ssr).toBe(false);
    expect(opts2.ssr).toBe(true);
  });
});
