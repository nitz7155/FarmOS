# Frontend E2E Tests (Playwright)

> **Status**: Test specs 작성됨. Playwright 패키지는 미설치 상태.
>
> 활성화 방법:
> ```bash
> cd frontend
> pnpm add -D @playwright/test
> # 또는 npm:
> npm install -D @playwright/test
>
> # Browser binaries 설치 (최초 1회)
> npx playwright install chromium
>
> # 실행
> npx playwright test tests/e2e/agent-action-history.spec.ts
> ```

## 전제 조건

Spec 실행 시 다음이 모두 기동되어 있어야 합니다:

| 서비스 | 주소 | 비고 |
|--------|------|------|
| FarmOS BE | http://localhost:8000 | `start-all.bat` 으로 기동 |
| FarmOS FE | http://localhost:5173 | Vite dev server |
| N100 Relay | https://iot.lilpa.moe | (L3 시나리오 E2) 실서비스 또는 mock |

로그인 세션 쿠키(`farmos_token`)가 필요합니다. 개별 spec 상단의 `beforeAll` 에서 로그인 API 를 호출하거나 `playwright.config.ts` 의 `storageState` 로 프리로그인 세션을 재사용하세요.

## 시나리오 목록 (Design §8.4 / §8.5)

**agent-action-history.spec.ts**
- U1: 대시보드 로드 → Summary Cards 4개 가시
- U2: 탭 7일 클릭 → `/activity/summary?range=7d` 호출
- U3: 더보기 클릭 → `/decisions?cursor=` 호출, 목록 20→40
- U4: row 클릭 → DetailModal 오픈, 섹션 5개 모두 표시
- U5: Copy 버튼 → clipboard 에 action JSON 존재
- U6: Esc → Modal close + focus 원복
- E1: 전체 플로우 (Load → Summary → List → More → Detail → Copy → Esc)
- E3: Bridge 비활성화 상태에서도 FE 오류 없음 (목록 빈 배열)

## Config 샘플 (`playwright.config.ts`)

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
```
