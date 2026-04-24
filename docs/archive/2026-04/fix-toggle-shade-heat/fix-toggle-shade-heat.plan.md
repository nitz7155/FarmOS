# Fix Toggle: 차광/보온 동기화 Planning Document

> **Summary**: ESP8266 D3 버튼이 차광(shade)만 토글하고 보온(heating)은 건드리지 않던 firmware 누락, 그리고 rule 분기에서 broadcast/persist 순서가 반대인 backend 불변식 위반, 그리고 ShadingCard 만 debounce 경로를 쓰는 frontend 비대칭을 한 번에 바로잡아 "조명/환기와 동일한 체감 응답성 + OFF 전환 100% 신뢰성" 을 확보한다.
>
> **Project**: FarmOS - IoT Manual Control Reliability
> **Version**: 0.1.0
> **Feature**: fix-toggle-shade-heat
> **Date**: 2026-04-24
> **Status**: Draft
> **Prerequisites**: `iot-manual-control`, `manual-control-onoff` (archived) 완료 — 4대 카드 + Relay `/control` API + `useManualControl` 훅 + ESP8266 폴링 경로 존재

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | ESP8266 D3 버튼을 누르면 차광막과 보온커튼이 하나로 일괄 제어되어야 하는데(HW 제약), 현재 firmware 는 `shadeOn` 만 토글하고 `reportButton("shading", ...)` 만 전송한다. 보온은 버튼 이벤트가 생성조차 되지 않아 대시보드에서 이전 상태로 남는다. 더해 백엔드 rule 분기에서 SSE broadcast 가 DB persist 보다 먼저 일어나 Bridge UPSERT(`ON CONFLICT DO NOTHING`)가 빈 tool_calls 레코드를 락인하며, 프론트 ShadingCard 는 300ms debounce 경로(`sendCommand`)를 사용해 조명/환기(`sendCommandImmediate`)보다 체감이 느리다. |
| **Solution** | (1) firmware `checkButtons()` 의 shade 분기에서 `shadeOn = heatingOn = !shadeOn` 로 동시 토글하고 `reportButton` 을 두 번 호출, 마지막에 `return` 을 추가한다. (2) `ai_agent.py` line 546-547 / 603-604 의 broadcast↔persist 호출 순서를 tool 분기(line 386-387)와 동일하게 `persist → broadcast` 로 뒤집는다. (3) `ManualControlPanel.tsx` ShadingCard 마스터 토글을 `sendCommandImmediate` 로 교체하고, 하나의 payload 로 `shade_pct=0, insulation_pct=0` 을 함께 보내 원자적 OFF 를 달성한다. |
| **Function/UX Effect** | D3 버튼 1회 = 차광 LED + 보온 LED 동시 전환, 대시보드 카드 2개 동시 갱신. OFF 누르면 항상 OFF 로 복귀. 체감 응답시간이 조명/환기와 동일 수준(≤ 1초). 보온이 유령처럼 켜져 있는 증상 소멸. |
| **Core Value** | **현장 운용자의 신뢰 회복**. 차광/보온은 농작물 스트레스와 직결되는 환경 제어라 "껐다고 했는데 안 꺼졌다" 는 체감은 단순 UX 불편이 아니라 재배 손실 리스크. 하드웨어 제약(핀 부족으로 D3 공용)을 유지한 채 소프트웨어 3 레이어 fix 로 SSoT 일관성을 복원한다. |

---

## Context Anchor

> Auto-propagated to Design/Do/Analysis documents for cross-session context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 차광/보온이 D3 핀 공용 제어라는 HW 계약을 firmware/backend/frontend 어느 레이어도 충실히 반영하지 못하여 "수동 OFF 했는데 보온이 ON 상태로 남음" + "토글 반응 느림" 두 증상이 동시 발생 |
| **WHO** | FarmOS 대시보드 사용자(1인 농업인), 현장에서 ESP8266 물리 버튼과 웹 토글을 병행 사용. 보온·차광은 야간 농작물 보호와 직결 |
| **RISK** | (1) firmware 재배포 중 실시간 측정 스트림 단절(ESP8266 현재 운용 중) (2) backend 순서 수정이 기존 rule 분기 retry 경로에 사이드이펙트 (3) 프론트 `sendCommandImmediate` 전환 시 기존 debounce 가 흡수하던 UI 과다 호출이 서버로 그대로 전달 — rate limit 필요성 검토 |
| **SUCCESS** | SC-1: D3 1회 누름 → SSE 에 shading + heating 이벤트 두 개 도착(간격 ≤ 100ms) / SC-2: 10회 연속 토글 시 차광/보온 OFF 전환 실패율 0% / SC-3: 대시보드 체감 응답 시간이 조명/환기와 ±200ms 이내 / SC-4: `ai_agent_decisions` 테이블에서 rule 소스 row 도 tool_calls/reasoning_trace 비어있지 않음 / SC-5: 조명·환기·관수 회귀 0건 |
| **SCOPE** | firmware: `DH11_KY018_WiFi.ino` checkButtons() 의 shade 분기 확장 / backend: `iot_relay_server/app/ai_agent.py` line 546-547, 603-604 순서 수정 / frontend: `ManualControlPanel.tsx` ShadingCard 마스터 토글 경로 전환 + useManualControl 영향 검토. Out: lock TTL, control_store partial-update 보정, UI 카드 통합 |

---

## 1. Overview

### 1.1 Purpose

ESP8266 D3 핀에 물리적으로 바인딩된 차광막/보온커튼 일괄 제어가 소프트웨어 전 계층에서 "하나의 논리 액션 = 두 액추에이터 동시 전환" 계약으로 관철되도록 3개 레이어를 동기화한다. 조명·환기 토글과 동일한 응답성을 차광·보온에도 제공하고, OFF 상태가 누락 없이 대시보드·DB·Bridge 까지 전파되는 것을 보장한다.

### 1.2 Background

- **HW 계약**: 차광과 보온은 별도 GPIO 를 쓸 여유가 없어서 D3 푸시 버튼 1개가 두 릴레이(차광막, 보온커튼)를 일괄 제어하는 구조로 결정되었다. (프로젝트 메모: `project_esp8266_pin_binding.md`)
- **firmware 현재 상태** (`DH11_KY018_WiFi.ino`):
  - line 48-57: `shadeOn` 플래그만 존재, `heatingOn` 플래그 없음
  - line 55-57: `shadePressed` 인터럽트 플래그만 존재, `heatingPressed` 없음
  - line 62: `onShadeBtn()` IRAM 핸들러만 존재
  - line 162-168: `shadePressed` 분기에서 `shadeOn` 만 토글하고 `reportButton("shading", shadeOn)` 1회 호출, **line 168에 `return;` 누락**
  - line 238-269 `applyCommand()`: heating control_type case 없음 (서버가 내려보낸 heating 명령 역시 무시됨)
- **backend 현재 상태** (`iot_relay_server/app/ai_agent.py`):
  - line 378-387 tool 분기: `await _persist_decision(d)` → `_broadcast_store("ai_decision", d)` (✅ 올바름)
  - line 542-547 rule 분기: `_broadcast("ai_decision", d)` → `await _persist_decision(d)` (❌ 반대 — `reasoning_trace/tool_calls` 부착 전에 SSE 로 나감)
  - line 600-604 추가 분기: 동일한 역순 (❌)
  - 프로젝트 메모 `project_iot_relay_llm_pipeline.md` 에 명시된 불변식 위반
- **frontend 현재 상태** (`ManualControlPanel.tsx` + `useManualControl.ts`):
  - `LightingCard` 마스터 토글 = `sendCommandImmediate('lighting', ...)` (즉시 POST)
  - `VentilationCard` ON/OFF = `sendCommandImmediate('ventilation', ...)` (즉시 POST)
  - `ShadingCard` 마스터 토글 = `sendCommand('shading', ...)` (300ms debounce)
  - 차광 OFF 가 `shade_pct=0 && insulation_pct=0` 복합 조건이라, 두 슬라이더를 각각 0 으로 내려야 OFF 가 전파됨

### 1.3 Related Documents

- 선행 Plan: `FarmOS/docs/01-plan/features/iot-manual-control.plan.md`
- 선행(archived): `FarmOS/docs/archive/2026-04/manual-control-onoff/*`
- 프로젝트 불변식 메모: `project_esp8266_pin_binding.md`, `project_iot_relay_llm_pipeline.md`
- 구현체: `FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino`, `iot_relay_server/app/ai_agent.py`, `iot_relay_server/app/control_store.py`, `FarmOS/frontend/src/modules/iot/ManualControlPanel.tsx`, `FarmOS/frontend/src/hooks/useManualControl.ts`

---

## 2. Scope

### 2.1 In Scope

**firmware-team**
- [ ] `heatingOn`, `heatingPressed` 플래그 추가(또는 shade 에 동기)
- [ ] `checkButtons()` shade 분기에서:
  - `shadeOn = !shadeOn; heatingOn = shadeOn;` (or 별도 토글이지만 HW 계약상 동기)
  - `reportButton("shading", shadeOn);` + `reportButton("heating", heatingOn);` 두 번 호출
  - 마지막 줄에 `return;` 추가 (line 168 위치)
- [ ] `mirrorLeds()` 에 보온 LED 가 있으면 그것도 `heatingOn` 에 맞춰 갱신 (없으면 shade LED 와 공유 유지 — 현 하드웨어 그대로)
- [ ] `applyCommand()` 에 `heating` case 추가 (서버가 heating on/off 내려보내면 heatingOn 갱신)
- [ ] 빌드 → 현장 ESP8266 에 OTA 또는 USB 재플래시

**backend-team**
- [ ] `iot_relay_server/app/ai_agent.py` line 546-547 순서 뒤집기: `await _persist_decision(d)` → `_broadcast("ai_decision", d)`
- [ ] 동일 수정 line 603-604
- [ ] 순서 뒤집기 이후 `reasoning_trace` 가 비어있는 rule 케이스의 표시 규약 확정 — 비어있어도 SSE 페이로드에 `reasoning_trace: []` 로 명시 보내서 Bridge UPSERT 가 tool_calls 없어도 새 row 로 인식하도록 (DO NOTHING 의 스키마 조건 검토)
- [ ] unit 또는 integration 레벨에서 ai_decision SSE 페이로드가 persist 된 row 와 id 일치하는지 검증하는 테스트 1개 추가 (조건 허용 시)

**frontend-team**
- [ ] `ManualControlPanel.tsx` ShadingCard 마스터 토글(`onMaster` 호출부) 을 `sendCommandImmediate` 경로로 교체
- [ ] 마스터 OFF 시 `{ shade_pct: 0, insulation_pct: 0, on: false }` 를 하나의 payload 로 전송 (원자적 OFF)
- [ ] `useManualControl.ts` `handleControlEvent` 에서 source='button' 이벤트 도착 시 해당 control_type 의 optimistic lock 을 즉시 해제 (race 방지)
- [ ] 차광 카드가 shading + heating 두 이벤트를 모두 받아서 렌더에 반영되는지 확인 (현재도 분리 컨트롤이므로 동작은 하겠으나 검증)
- [ ] playwright e2e: 차광 OFF 버튼 1회 클릭 → 5초 내에 heating on=false SSE 수신 확인 시나리오 1개 추가

### 2.2 Out of Scope

- `control_store.py` 의 `locked=True` 자동 해제 TTL (별도 feature 로 분리)
- `ai_agent_bridge.py` UPSERT 를 `ON CONFLICT DO UPDATE` 로 바꾸는 스키마 변경 (Bridge 계약 변경은 큰 폭이라 별도 feature)
- UI 를 "차광/보온 통합 카드" 로 물리적으로 합치는 작업 (사용자 선호상 별도 카드 유지)
- heating 전용 GPIO 추가 (HW 제약 — 프로젝트 불변식)

---

## 3. Root Cause Analysis (3 layers)

### 3.1 Firmware 계층 (가장 강한 원인)

| 버그 | 위치 | 결과 |
|---|---|---|
| shade 분기에 `return;` 누락 | `.ino` line 168 | 동일 루프 틱에서 이후 조건도 평가되며 타이밍 불안정 |
| `heatingOn/heatingPressed` 미정의 + D3 핸들러 단일 action | `.ino` line 48-62 + line 162-168 | D3 물리 버튼 1회 = `shadeOn` 만 토글. 보온은 이전 상태 고착 |
| `applyCommand()` heating case 없음 | `.ino` line 238-269 | 서버 측 rule/tool 이 heating 내려도 ESP8266 은 무시 |

### 3.2 Backend 계층 (데이터 신뢰도 원인)

| 버그 | 위치 | 결과 |
|---|---|---|
| broadcast → persist 역순 | `ai_agent.py:546-547`, `603-604` | SSE 가 DB 보다 먼저 나가 reasoning_trace 비어 있음. Bridge UPSERT(ON CONFLICT DO NOTHING)가 빈 tool_calls row 를 락인 → 이후 제대로 된 persist 가 덮어쓰지 못함 |

### 3.3 Frontend 계층 (체감 지연 원인)

| 비대칭 | 위치 | 결과 |
|---|---|---|
| ShadingCard 만 300ms debounce | `ManualControlPanel.tsx` assembly + `useManualControl.ts:85-122` | 조명/환기는 즉시 POST, 차광은 300ms 지연 → 사용자 체감상 차광만 굼뜸 |
| 차광 OFF 가 2-슬라이더 복합 조건 | `ManualControlPanel.tsx:361-379` | 원자적 OFF 버튼 없어 shade_pct+insulation_pct 각각 0 처리 중 race 발생 가능 |

---

## 4. Functional Requirements

- **FR-01**: firmware D3 버튼 1회 인터럽트 = shadeOn XOR + heatingOn 동기화 + 두 reportButton 호출
- **FR-02**: firmware checkButtons() shade 분기 종료 시 `return;`
- **FR-03**: firmware applyCommand() 가 control_type="heating" 페이로드를 수신하고 heatingOn 을 갱신
- **FR-04**: backend ai_agent.py 모든 분기에서 persist 완료 후 broadcast (프로젝트 불변식 전면 적용)
- **FR-05**: frontend ShadingCard 마스터 토글 경로가 `sendCommandImmediate` 사용
- **FR-06**: 차광 OFF 1 클릭 = `{shade_pct:0, insulation_pct:0, on:false}` 단일 POST
- **FR-07**: source='button' SSE 이벤트 수신 시 프론트 optimistic lock 즉시 해제

## 5. Non-Functional Requirements

- **NFR-01**: 차광/보온 체감 응답 시간 ≤ 1s (조명/환기 수준)
- **NFR-02**: firmware 메모리 증가 ≤ 200 bytes (ESP8266 flash 여유 고려)
- **NFR-03**: backend 수정이 기존 tool 분기 retry 경로에 영향 없음 (회귀 0건)

## 6. Success Criteria

- **SC-1**: D3 버튼 1회 누름 → SSE 스트림에 `control_type=shading` + `control_type=heating` 두 이벤트 도착, 간격 ≤ 100ms ✅
- **SC-2**: 연속 10회 토글 시 차광 OFF / 보온 OFF 전환 실패 0/10 ✅
- **SC-3**: 대시보드 체감 응답 시간: 차광/보온 vs 조명/환기 차이 ≤ 200ms ✅
- **SC-4**: `ai_agent_decisions` 테이블에서 source='rule' row 도 `tool_calls`, `reasoning_trace` 컬럼이 `[]` 또는 값 있음 (NULL 금지) ✅
- **SC-5**: 조명·환기·관수 회귀 0건 (기존 기능 정상) ✅

## 7. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| ESP8266 재배포 중 실시간 측정 단절 | Medium | 펌웨어 빌드 먼저 → 사용자 승인 후 짧은 다운타임 창으로 재플래시. Serial 로 부팅 확인 |
| backend 순서 수정이 retry 경로 깨뜨림 | Medium | 수정 전 rule 분기 실행 경로 전수 정리, 수정 후 로컬에서 rule trigger 샘플 몇 건 → SSE + DB 확인 |
| `sendCommandImmediate` 전환으로 과다 호출 | Low | 현재 사용자 클릭 빈도상 문제 없음. 필요 시 후속 feature 에서 rate limit |
| Bridge UPSERT 가 persist 전 broadcast 로 이미 잠긴 row 는 여전히 덮어쓰지 못함 | Low | 본 feature 수정 이후 신규 row 는 정상. 기존 락인된 row 는 manual 쿼리로 갱신 (별도 운영 작업) |

## 8. Timeline (예상)

| Phase | Duration |
|---|---|
| Plan | 0.5h (이 문서) |
| Design (Option C 확정) | 0.5h |
| Do — 3팀 병렬 | 2h (firmware 빌드·플래시 1h 포함) |
| Check (ESP8266 실장비 검증) | 0.5h |
| Iterate/Report | 0.5h |
| **Total** | **≈ 4h** |

---
