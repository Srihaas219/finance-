import { defineConfig, devices } from "@playwright/test";

// Browser E2E against the REAL backend (no mocked API responses on the happy path).
// Two webServers: the FastAPI backend (fresh SQLite + demo seed) and the Vite dev server.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "bash e2e/backend-up.sh",
      url: "http://localhost:8000/readyz",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://localhost:5173",
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_URL: "http://localhost:8000" },
    },
  ],
});
