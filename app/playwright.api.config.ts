import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.api.spec.ts',
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: 'http://127.0.0.1:5183',
    viewport: { width: 390, height: 844 },
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5183 --strictPort',
    url: 'http://127.0.0.1:5183',
    env: { VITE_USE_MOCKS: 'false', VITE_MAX_BRIDGE_URL: '', VITE_PROXY_TARGET: process.env.E2E_API_URL || 'http://127.0.0.1:8001', VITE_DEV_USER: '1' },
    reuseExistingServer: false,
  },
});
