# IoT Manual Control — Completion Report

> **Feature**: iot-manual-control
> **Date**: 2026-04-16
> **Match Rate**: 98%
> **Status**: Completed (module-1~3), module-4 Pending (하드웨어)

---

## 1. Executive Summary

### 1.1 Feature Overview

| Perspective | Planned | Delivered |
|-------------|---------|-----------|
| **Problem** | IoT 시스템이 센서 모니터링만 가능, 수동 제어 및 하드웨어 양방향 연동 부재 | Relay Server 제어 API 6개 + Frontend 수동 제어 UI + AI Agent 통합 완료 |
| **Solution** | 프론트엔드 4대 제어 UI + ESP8266 버튼/LED + Relay Server 중계 | control_store(Single Source of Truth) + ManualControlPanel + 시뮬레이션 모드 |
| **Function/UX** | 슬라이더/토글로 제어, LED 양방향 동기화, 시뮬레이션 모드 | 낙관적 업데이트 + ControlSlider + sendCommandImmediate + 자물쇠 잠금/해제 |
| **Core Value** | PC 대시보드 또는 현장 버튼으로 즉시 제어 가능한 통합 경험 | AI/수동/버튼 3개 소스가 하나의 파이프라인 공유, 수동 잠금으로 AI 오버라이드 방지 |

### 1.2 Value Delivered

| Metric | Target | Actual |
|--------|--------|--------|
| Match Rate | >= 90% | **98%** |
| API Endpoints | 5개 | **6개** (unlock 추가) |
| L1 Runtime Tests | Pass | **9/9 PASS** |
| Module 완료 | 4/4 | **3/4** (module-4 하드웨어 대기) |
| Critical Issues | 0 | **0** |

---

## 2. PDCA Cycle Summary

| Phase | Date | Output | Status |
|-------|------|--------|:------:|
| Plan | 2026-04-16 | `docs/01-plan/features/iot-manual-control.plan.md` | Done |
| Design | 2026-04-16 | `docs/02-design/features/iot-manual-control.design.md` | Done |
| Do (module-1) | 2026-04-16 | Relay Server API + AI Agent 통합 | Done + Deployed |
| Do (module-2,3) | 2026-04-16 | Frontend 훅 + UI | Done |
| Do (module-4) | - | ESP8266 펌웨어 | Pending |
| Check | 2026-04-16 | `docs/03-analysis/iot-manual-control.analysis.md` | 98% |
| Report | 2026-04-16 | 이 문서 | Done |

---

## 3. Key Decisions & Outcomes

| # | Decision | Source | Followed | Outcome |
|---|----------|--------|:--------:|---------|
| 1 | ESP8266 양방향 통신: 폴링 방식 | Plan | Yes | ESP8266 메모리 안정성 확보, 2~3초 폴링 주기 설계 |
| 2 | 제어 상태: 인메모리 + 파일 백업 | Plan | Yes | control_state.json으로 Docker 재시작 시 복원 |
| 3 | Option C: Pragmatic Balance | Design | Yes | 신규 4파일 + 수정 7파일로 적정 규모 |
| 4 | AI Agent 통합 (Single Source of Truth) | Do 중 결정 | Yes | ai_agent.py 30곳 리팩토링, 3소스(AI/수동/버튼) 통합 |
| 5 | 수동 잠금(locked) 기능 | Do 중 결정 | Yes | AI 일반규칙 오버라이드 방지, 자물쇠 UI |
| 6 | API_BASE https (Cloudflare CORS) | Do 중 발견 | Yes | HTTP→HTTPS redirect로 preflight 실패 해결 |
| 7 | ControlSlider (드래그 중 로컬 state) | Do 중 결정 | Yes | 슬라이더 snap-back 문제 해결 |
| 8 | sendCommand/sendCommandImmediate 분리 | Do 중 결정 | Yes | 슬라이더(디바운스) vs 버튼(즉시) 분리 |

---

## 4. Implementation Details

### 4.1 Relay Server (iot_relay_server/app/)

| File | Type | Lines | Description |
|------|------|:-----:|-------------|
| control_store.py | NEW | ~180 | 인메모리 상태 + locked + 명령 큐 + 파일 영속화 |
| control_routes.py | NEW | ~60 | 6개 API 엔드포인트 |
| schemas.py | MOD | +25 | 4개 Pydantic 스키마 |
| main.py | MOD | +8 | 라우터 등록 + startup |
| ai_agent.py | MOD | ~60 | control_store 통합, is_manual_override_active |
| tools/executor.py | MOD | ~40 | 4개 제어 핸들러 control_store 경유 |

### 4.2 Frontend (FarmOS/frontend/src/)

| File | Type | Lines | Description |
|------|------|:-----:|-------------|
| hooks/useManualControl.ts | NEW | ~150 | sendCommand + sendCommandImmediate + simulate + unlock |
| modules/iot/ManualControlPanel.tsx | NEW | ~380 | 4개 제어 카드 + ControlSlider + LockButton + SimulationBar |
| hooks/useSensorData.ts | MOD | +20 | SSE control + ai_decision 콜백 |
| hooks/useAIAgent.ts | MOD | +30 | SSE ai_decision 즉시 반영, decisions fetch |
| modules/iot/IoTDashboardPage.tsx | MOD | +2 | ManualControlPanel 임포트 |
| types/index.ts | MOD | +50 | ManualControlState 등 7개 타입 |
| modules/iot/AIAgentPanel.tsx | MOD | +15 | decisions 여러 건 표시 |

---

## 5. Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|----------|:------:|---------|
| SC-1 | 프론트엔드 4개 제어 UI 동작 | Met | ManualControlPanel: 환기/관수/조명/차광 카드 |
| SC-2 | ESP8266 버튼 → LED → 프론트엔드 반영 | Partial | 시뮬레이션 모드로 검증 완료, 실 하드웨어 미테스트 |
| SC-3 | 프론트엔드 → ESP8266 LED 반응 | Partial | API 경로 검증 완료, 실 하드웨어 미테스트 |
| SC-4 | 양방향 동기화 | Met | SSE control 이벤트로 즉시 반영 |
| SC-5 | 제어 상태 영속화 | Met | control_state.json 저장/복원 |
| SC-6 | AI Agent 통합 | Met | control_store Single Source of Truth |
| SC-7 | 수동 잠금/해제 | Met | locked 필드 + 자물쇠 UI |

**Overall: 5/7 Met, 2/7 Partial** (하드웨어 의존 항목)

---

## 6. Design-Beyond Implementations (15건)

구현 과정에서 Design 문서에 없지만 추가된 개선사항:

1. **locked 필드** — 수동 잠금/해제 (AI 오버라이드 방지)
2. **POST /control/unlock** — 잠금 해제 API
3. **ControlSlider** — 드래그 중 로컬 state, 놓으면 서버 전송
4. **sendCommandImmediate** — 버튼용 즉시 실행 (디바운스 없음)
5. **SSE ai_decision 리스너** — AI 판단 즉시 UI 반영
6. **5초 AI SSE 가드** — 수동 조작 직후 AI SSE 무시
7. **get_control_state_for_ai()** — AI용 정제 상태
8. **reset_daily_irrigation()** — 일일 관수량 리셋
9. **관수 추가 필드** — daily_total_L, last_watered, nutrient
10. **낙관적 업데이트** — API 응답 전 UI 즉시 반영
11. **API_BASE https** — Cloudflare CORS 해결
12. **LockButton 컴포넌트** — 자물쇠 UI
13. **onAIDecisionEvent** — AI 판단 콜백 시스템
14. **credentials: 'omit'** — CORS 호환성
15. **팬 속도 이산 버튼** — 슬라이더 대신 0/500/1000/1500/3000 RPM

---

## 7. Issues Encountered & Resolved

| # | Issue | Root Cause | Resolution |
|---|-------|-----------|------------|
| 1 | AI Agent 판단 이력 1건만 표시 | `latest_decision` 1건만 반환, decisions API 미사용 | useAIAgent에 `/decisions` fetch 추가 |
| 2 | 슬라이더 값이 0%로 복귀 | AI 규칙이 수동 제어를 덮어씀 + SSE echo | locked 필드 + ControlSlider (로컬 drag state) |
| 3 | CORS preflight 실패 | Cloudflare HTTP→HTTPS redirect | API_BASE를 https로 변경 |
| 4 | 관수/조명 자물쇠 미작동 | sendCommand 디바운스 300ms로 POST 지연 | sendCommandImmediate (즉시 실행) 분리 |
| 5 | AI Agent 반응 느림 | 30초 폴링 의존 | SSE ai_decision 이벤트로 즉시 반영 |

---

## 8. Remaining Work

| Item | Priority | Description |
|------|:--------:|-------------|
| module-4: ESP8266 펌웨어 | High | 버튼/LED 회로 구성 후 폴링 루프 + ISR 구현 |
| Design 문서 갱신 | Low | locked/unlock, ControlSlider 등 15건 반영 |
| 시뮬레이션 API Key 노출 | Low | 개발 환경 trade-off로 수용 |

---

## 9. Architecture Diagram (Final)

```
┌──────────────────────────────────────────────────────────────┐
│ Frontend (React, localhost:5173)                              │
│                                                              │
│   ManualControlPanel ──→ useManualControl                    │
│     ├─ ControlSlider (드래그: 로컬, 놓으면: sendCommand)      │
│     ├─ 밸브/ON-OFF 버튼 → sendCommandImmediate               │
│     ├─ LockButton → unlockControl                            │
│     └─ SimulationBar → simulateButton                        │
│                                                              │
│   useSensorData ──→ SSE(control, ai_decision) ──→ callbacks  │
│   useAIAgent ──→ SSE ai_decision + 60s polling fallback      │
│                                                              │
│   API_BASE: https://iot.lilpa.moe (Cloudflare TLS 종료)      │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTPS
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ Cloudflare (TLS Termination)                                 │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ IoT Relay Server (N100, Docker, FastAPI)                      │
│                                                              │
│   control_routes.py ──→ control_store.py (Single Source)     │
│     POST /control         update_control_state()             │
│     GET  /control/state   get_control_state()                │
│     GET  /control/commands get_and_clear_pending()            │
│     POST /control/report  update_control_state(button)       │
│     POST /control/ack     clear_acknowledged()               │
│     POST /control/unlock  unlock_control()                   │
│                                                              │
│   ai_agent.py ──→ control_store (읽기/쓰기)                  │
│     규칙 엔진 → is_manual_override_active() 체크 후 실행      │
│     긴급 규칙 → locked 무시                                   │
│                                                              │
│   store.py → SSE _broadcast("control", "ai_decision")        │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP (:9000 직접)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ ESP8266 (module-4, 미구현)                                    │
│   GET  /control/commands (2~3초 폴링)                        │
│   POST /control/report (버튼 누름 시)                        │
│   POST /control/ack (명령 수신 확인)                          │
└──────────────────────────────────────────────────────────────┘
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-16 | Initial report — module-1~3 완료, 98% match rate |
