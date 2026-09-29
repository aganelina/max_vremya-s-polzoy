import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testIgnore: '**/*.api.spec.ts',
  fullyParallel: true,
  workers: 3,
  use: {
    baseURL: 'http://127.0.0.1:5182',
    viewport: { width: 390, height: 844 },
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5182 --strictPort',
    url: 'http://127.0.0.1:5182',
    env: { VITE_USE_MOCKS: 'true', VITE_MAX_BRIDGE_URL: '', VITE_BOT_USERNAME: 'vremya_test_bot' },
    reuseExistingServer: false,
  },
});
