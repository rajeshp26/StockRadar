import { defineConfig, devices } from "@playwright/test";

// Responsive validation is a REQUIRED concern in framework/frontend_stack.yaml.
// G5 asserts at least two viewport/device projects exist, so a "responsive" claim
// is backed by more than one rendered width.
export default defineConfig({
  testDir: "tests/e2e",
  outputDir: "framework/telemetry/browser/artifacts",
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run preview",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "tablet",  use: { ...devices["iPad (gen 7)"] } },
    { name: "mobile",  use: { ...devices["Pixel 7"], viewport: { width: 393, height: 852 } } },
  ],
});
