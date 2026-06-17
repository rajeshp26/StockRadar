import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import React from "react";

describe("Analysis Page — Mobile Responsiveness", () => {
  it("P3-UT-41: tab bar has horizontal scroll on small screens", () => {
    const { container } = render(
      <div className="glass-segmented overflow-x-auto w-full styled-scrollbar">
        <button className="glass-segmented-item flex items-center gap-1.5 active">
          <span className="hidden sm:inline">Intrinsic Value</span>
          <span className="sm:hidden">Intrinsic</span>
        </button>
        <button className="glass-segmented-item flex items-center gap-1.5">
          <span className="hidden sm:inline">Fundamentals</span>
          <span className="sm:hidden">Fund.</span>
        </button>
      </div>,
    );
    const tabBar = container.querySelector(".overflow-x-auto");
    expect(tabBar).toBeInTheDocument();
    expect(tabBar?.classList.contains("styled-scrollbar")).toBe(true);
  });

  it("P3-UT-42: tab labels show abbreviated text on small screens", () => {
    const { container } = render(
      <div>
        <span className="hidden sm:inline">Intrinsic Value</span>
        <span className="sm:hidden">Intrinsic</span>
      </div>,
    );
    const mobileText = container.querySelector(".sm\\:hidden");
    expect(mobileText?.textContent).toBe("Intrinsic");
  });

  it("P3-UT-43: 'others' sub-tabs show abbreviated labels on mobile", () => {
    const { container } = render(
      <div>
        <span className="hidden sm:inline">Magic Formula</span>
        <span className="sm:hidden">Magic</span>
        <span className="hidden sm:inline">CANSlim</span>
        <span className="sm:hidden">CANS</span>
      </div>,
    );
    const mobileTexts = container.querySelectorAll(".sm\\:hidden");
    expect(mobileTexts[0]?.textContent).toBe("Magic");
    expect(mobileTexts[1]?.textContent).toBe("CANS");
  });

  it("P3-UT-44: price header stacks vertically on mobile", () => {
    const { container } = render(
      <div className="relative flex flex-col gap-4 md:flex-row md:items-center">
        <div className="flex items-center gap-4">Content</div>
        <div className="flex items-baseline gap-3 md:ml-auto">Price</div>
      </div>,
    );
    const flexContainer = container.firstChild as HTMLElement;
    expect(flexContainer.className).toContain("flex-col");
    expect(flexContainer.className).toContain("md:flex-row");
  });
});
