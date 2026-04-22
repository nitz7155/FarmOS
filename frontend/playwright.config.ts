/**
 * Playwright 설정 — agent-action-history feature E2E.
 *
 * 실행:
 *   cd frontend
 *   # BE + FE 기동 상태 가정
 *   npx playwright test tests/e2e/agent-action-history.spec.ts
 *
 * globalSetup 이 farmer01 계정으로 로그인 후 storageState 저장.
 * 모든 test 는 이 세션을 재사용.
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false, // 로그인 세션 공유로 순차 실행
  retries: 0,
  reporter: 'list',
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    baseURL: 'http://localhost:5173',
    storageState: 'tests/e2e/.auth/farmer01.json',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
