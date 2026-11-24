import { defineConfig } from "@playwright/test";

// The tests run inside the Playwright container sharing Caddy's network; global-setup
// forwards localhost:8080 to Caddy, the same address users and signed links use.
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  outputDir: "results",
  use: {
    baseURL: process.env["E2E_BASE_URL"] ?? "http://localhost:8080",
    locale: "pt-BR",
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
