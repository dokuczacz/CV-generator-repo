import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  // Hard default timeout to prevent "stuck" runs.
  // Individual tests can override with `test.setTimeout(...)`.
  timeout: 300_000,
  expect: {
    timeout: 20_000,
  },

  reporter: [['line'], ['html', { open: 'never' }]],
  reportSlowTests: {
    max: 10,
    threshold: 60_000,
  },

  // Ensure the UI + Azure Functions are started fresh for tests.
  // Set `PW_REUSE_SERVER=1` to reuse already-running dev servers.
  webServer: [
    {
      command: 'node scripts/playwright-start-backend.js',
      url: 'http://127.0.0.1:7071/api/health',
      reuseExistingServer: process.env.PW_REUSE_SERVER === '1',
      timeout: 300_000,
    },
    {
      command: 'node scripts/playwright-start-frontend.js',
      url: 'http://127.0.0.1:3000',
      reuseExistingServer: process.env.PW_REUSE_SERVER === '1',
      timeout: 300_000,
    },
  ],
  
  use: {
    // Always keep trace/video on failure so timeouts are debuggable.
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Output folder for test artifacts
  outputDir: 'test-results/',
});
