import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 60000,
  expect: { timeout: 20000 },
  use: {
    baseURL: "http://127.0.0.1:8765",
    headless: true,
  },
  webServer: {
    command: "python3 serve_dashboards.py",
    cwd: new URL(".", import.meta.url).pathname,
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: true,
    timeout: 120000,
  },
});
