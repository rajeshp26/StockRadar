import { test, expect } from "@playwright/test";

// Browser evidence for requirement shapes that no unit test can prove.
// Each test names the requirement shape it covers, per .opencode/rules/evidence.md.

test.describe("REQ-017 session refresh — visible behaviour", () => {
  test.beforeEach(async ({ page }) => {
    // Transport is mocked at the network boundary: this spec proves FRONTEND visible
    // behaviour (interaction flow, console cleanliness, alignment, responsiveness).
    // The /auth/refresh request/response SHAPE is proven against the real backend by
    // the G1 contract tests (tests/contract/test_api_004.py); duplicating the live
    // call here would make browser evidence depend on a running backend. The
    // fulfilment body is the generated RefreshResponse (src/frontend/contracts/api_004.ts).
    await page.route("**/auth/refresh", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "e2e-access-token",
          expires_in: 900,
          token_type: "Bearer",
        }),
      }),
    );
    await page.goto("/");
  });

  // shape: interaction flow end to end
  test("refreshing shows a success result", async ({ page }) => {
    await page.getByTestId("refresh-button").click();
    await expect(page.getByTestId("refresh-success")).toBeVisible();
    await expect(page.getByTestId("refresh-success")).toContainText(/expires in \d+s/i);
  });

  // shape: visual alignment / styling — DOM inspection, not a screenshot diff,
  // so the assertion states a measurable fact rather than "looks right".
  test("card is horizontally centred within the viewport", async ({ page }) => {
    const card = page.getByTestId("session-card");
    const box = (await card.boundingBox())!;
    const vw = page.viewportSize()!.width;
    const leftGap = box.x;
    const rightGap = vw - (box.x + box.width);
    expect(Math.abs(leftGap - rightGap)).toBeLessThanOrEqual(2);
  });

  // shape: console must be clean — a silent React error is a real defect
  test("no console errors during refresh", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));
    await page.getByTestId("refresh-button").click();
    await expect(page.getByTestId("refresh-success")).toBeVisible();
    expect(errors).toEqual([]);
  });
});

// shape: responsive behaviour — runs under every configured viewport project,
// which is why G5 requires at least two.
test("action button spans full width only on narrow viewports", async ({ page }) => {
  await page.goto("/");
  const btn = page.getByTestId("refresh-button");
  const card = page.getByTestId("session-card");
  const b = (await btn.boundingBox())!;
  const c = (await card.boundingBox())!;
  const vw = page.viewportSize()!.width;
  if (vw < 640) {
    expect(b.width).toBeGreaterThan(c.width * 0.8);
  } else {
    expect(b.width).toBeLessThan(c.width * 0.8);
  }
});
