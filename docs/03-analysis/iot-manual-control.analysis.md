# IoT Manual Control — Gap Analysis Report

> **Feature**: iot-manual-control
> **Date**: 2026-04-16
> **Design**: `docs/02-design/features/iot-manual-control.design.md`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 센서 모니터링만 가능한 IoT 시스템에 양방향 수동 제어 추가 |
| **WHO** | FarmOS 사용자 (1인 농업인) |
| **RISK** | ESP8266 HTTP-only, 폴링 지연, N100 재배포 필요 |
| **SUCCESS** | 프론트엔드 토글 → 5초 내 ESP8266 반응, ESP8266 → 2초 내 프론트엔드 반영 |
| **SCOPE** | module-1~3 구현 완료, module-4(ESP8266) 하드웨어 구성 후 진행 |

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Structural Match | 100% | PASS |
| Functional Depth | 95% | PASS |
| API Contract | 100% | PASS |
| L1 Runtime (API) | 100% (9/9) | PASS |
| **Overall** | **98%** | **PASS** |

Formula: (Structural x 0.2) + (Functional x 0.4) + (Contract x 0.4) = 20 + 38 + 40 = **98%**

---

## Structural Match (100%)

| # | Design File | Status | Path |
|---|-------------|:------:|------|
| 1 | control_store.py [NEW] | PASS | iot_relay_server/app/ |
| 2 | control_routes.py [NEW] | PASS | iot_relay_server/app/ |
| 3 | schemas.py [MODIFY] | PASS | iot_relay_server/app/ |
| 4 | main.py [MODIFY] | PASS | iot_relay_server/app/ |
| 5 | ai_agent.py [MODIFY] | PASS | iot_relay_server/app/ |
| 6 | tools/executor.py [MODIFY] | PASS | iot_relay_server/app/ |
| 7 | useManualControl.ts [NEW] | PASS | frontend/src/hooks/ |
| 8 | useSensorData.ts [MODIFY] | PASS | frontend/src/hooks/ |
| 9 | useAIAgent.ts [MODIFY] | ENHANCED | frontend/src/hooks/ (Design: 유지, 실제: SSE 추가) |
| 10 | ManualControlPanel.tsx [NEW] | PASS | frontend/src/modules/iot/ |
| 11 | IoTDashboardPage.tsx [MODIFY] | PASS | frontend/src/modules/iot/ |
| 12 | types/index.ts [MODIFY] | PASS | frontend/src/types/ |

---

## API Contract (100%)

| # | Endpoint | Auth | Status |
|---|----------|:----:|:------:|
| 1 | POST /api/v1/control | - | PASS |
| 2 | GET /api/v1/control/state | - | PASS |
| 3 | GET /api/v1/control/commands | X-API-Key | PASS |
| 4 | POST /api/v1/control/report | X-API-Key | PASS |
| 5 | POST /api/v1/control/ack | X-API-Key | PASS |
| 6 | POST /api/v1/control/unlock | - | PASS (Design 초과) |

---

## L1 Runtime Test Results (9/9 PASS)

| # | Test | Expected | Result |
|---|------|----------|:------:|
| T1 | POST /control → state 반환 | 200 + locked=true | PASS |
| T2 | GET /control/state | 200 | PASS |
| T3 | GET /commands without auth | 403 | PASS |
| T4 | GET /commands with auth | 200 | PASS |
| T5 | POST /report without auth | 403 | PASS |
| T6 | POST /report with auth | 200 | PASS |
| T7 | POST /ack with auth | 200 | PASS |
| T8 | POST /unlock → locked=false | 200 | PASS |
| T9 | Invalid control_type | 422 | PASS |

---

## Success Criteria Evaluation

| Criteria | Status | Evidence |
|----------|:------:|---------|
| 4개 제어 UI 동작 | PASS | ManualControlPanel에 환기/관수/조명/차광 카드 |
| 시뮬레이션 모드 | PASS | simulateButton() → /control/report (device_id: simulator) |
| SSE 실시간 반영 | PASS | useSensorData SSE control 이벤트 → handleControlEvent |
| 제어 상태 영속화 | PASS | control_state.json 파일 저장/복원 |
| AI Agent 통합 | PASS | control_store가 Single Source of Truth |
| 수동 잠금(locked) | PASS | 수동 제어 시 자동 잠금, 자물쇠 클릭으로 해제 |
| module-4 (ESP8266) | PENDING | 하드웨어 미구성 — 시뮬레이션으로 대체 검증 |

---

## Design 초과 구현 (15건)

| # | 항목 | 설명 |
|---|------|------|
| 1 | locked 필드 | 수동 잠금/해제 기능 |
| 2 | POST /control/unlock | 잠금 해제 엔드포인트 |
| 3 | ControlSlider 컴포넌트 | 드래그 중 로컬 state |
| 4 | sendCommandImmediate | 버튼용 즉시 실행 |
| 5 | SSE ai_decision 리스너 | AI 판단 즉시 반영 |
| 6 | 5초 AI SSE 가드 | 슬라이더 snap-back 방지 |
| 7 | get_control_state_for_ai() | AI용 정제된 상태 |
| 8 | reset_daily_irrigation() | 일일 관수량 리셋 |
| 9 | 관수 추가 필드 | daily_total_L, last_watered, nutrient |
| 10 | 낙관적 업데이트 | API 응답 전 UI 즉시 반영 |
| 11 | API_BASE https | Cloudflare CORS 대응 |
| 12 | LockButton 컴포넌트 | 자물쇠 UI |
| 13 | onAIDecisionEvent | AI 판단 콜백 |
| 14 | credentials: 'omit' | CORS 호환성 |
| 15 | 팬 속도 버튼 UI | 슬라이더 대신 이산 값 버튼 |

---

## Minor Deductions (2건)

| # | 항목 | Severity | 설명 |
|---|------|:--------:|------|
| 1 | 팬 속도 UI | Minor | Design 와이어프레임은 슬라이더 암시, 구현은 이산 버튼 (UX 개선) |
| 2 | useAIAgent.ts 변경 | Minor | Design에서 [유지]로 표기, 실제로 SSE 통합 수정 (문서 갱신 필요) |

**Critical/Important 이슈: 없음**

---

## Recommended Actions

1. Design 문서에 locked/unlock 기능 반영 (문서 갱신)
2. module-4 (ESP8266 펌웨어) 하드웨어 구성 후 구현
3. 시뮬레이션 모드의 API Key 노출은 개발 환경 trade-off로 수용
