import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e/golden-paths",
  fullyParallel: false,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run build && npm run preview",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    {
      name: "desktop-1366",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 720 } },
    },
    {
      name: "desktop-1920",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } },
    },
    {
      name: "tablet-834",
      use: {
        ...devices["iPad Pro 11"],
        browserName: "chromium",
        viewport: { width: 834, height: 1194 },
      },
    },
    {
      name: "mobile-390",
      use: {
        ...devices["Pixel 5"],
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: "mobile-430",
      use: {
        ...devices["Pixel 5"],
        browserName: "chromium",
        viewport: { width: 430, height: 932 },
      },
    },
  ],
});
