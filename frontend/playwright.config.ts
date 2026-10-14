import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:8010",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      process.platform === "win32"
        ? ".venv\\Scripts\\python.exe -m uvicorn tests.browser_server:app --host 127.0.0.1 --port 8010"
        : "python -m uvicorn tests.browser_server:app --host 127.0.0.1 --port 8010",
    cwd: "..",
    url: "http://127.0.0.1:8010/api/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
