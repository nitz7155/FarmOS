# Fix Toggle: 차광/보온 동기화 Design Document

> **Feature**: fix-toggle-shade-heat
> **Plan**: `FarmOS/docs/01-plan/features/fix-toggle-shade-heat.plan.md`
> **Version**: 0.1.0
> **Date**: 2026-04-24
> **Status**: Draft → ready for Do
> **Selected Architecture**: **Option C — Pragmatic Balance** (Plan 의 "권장" 범위와 동일)

---

## Context Anchor

> Propagated from Plan for cross-session continuity.

| Key | Value |
|-----|-------|
| **WHY** | 차광/보온이 D3 핀 공용 제어라는 HW 계약을 firmware/backend/frontend 3 레이어가 충실히 반영 못하여 "수동 OFF 후 보온이 켜짐" + "토글 반응 느림" 두 증상 동시 발생 |
| **WHO** | FarmOS 1인 농업인, ESP8266 물리 버튼과 웹 토글 병행 |
| **RISK** | ESP8266 재플래시 중 단절 / backend 순서 변경 회귀 / sendCommandImmediate 과다 호출 |
| **SUCCESS** | SC-1~5 (Plan 참조) |
| **SCOPE** | FW: shade 분기 확장 + applyCommand heating case / BE: ai_agent.py 546-547, 603-604 순서 / FE: ShadingCard 즉시 경로 + 원자 OFF. Out: lock TTL, UI 카드 통합 |

---

## Executive Summary

이번 fix 는 3 레이어에 분산된 세 버그를 **하나의 HW 계약("D3 버튼 = shade + heating 동시 토글")을 충실히 표현**하는 관점으로 정렬한다. firmware 가 Source of Truth 역할을 맡아 shade·heating 두 이벤트를 모두 방출하고, backend 는 프로젝트 불변식(persist → broadcast)을 일관 적용하며, frontend 는 조명/환기와 동일한 즉시 경로와 원자적 OFF 를 제공한다.

---

## 1. Overview

### 1.1 Goals

- firmware D3 인터럽트 1회 → shading + heating SSE 이벤트 2개 (간격 ≤100ms)
- backend rule/override 분기의 broadcast↔persist 순서 통일
- frontend ShadingCard 응답성을 조명/환기와 동등하게

### 1.2 Non-goals

- control_store.py `locked` 자동 해제 TTL (별도 feature)
- `ai_agent_bridge.py` UPSERT 스키마 변경 (`DO NOTHING` → `DO UPDATE`)
- UI 카드 물리적 통합 ("차광/보온 통합 카드")
- heating 전용 GPIO 추가 (HW 제약)

---

## 2. Architecture Options (요약)

| Option | 설명 | 변경 범위 | 회귀 위험 | 채택 |
|---|---|---|---|---|
| A. Minimal | firmware return 누락 + frontend sendCommandImmediate 교체 만 | 2 레이어, 4 줄 수준 | Low | ✗ 증상은 줄지만 backend 불변식 위반 잔존 |
| B. Clean | firmware 에 actuator 매핑 레이어 + backend 전체 broadcast 경로 리팩토링 + frontend hook 분리 | 3 레이어, 200+ lines | Medium | ✗ 시간/스코프 초과. YAGNI |
| **C. Pragmatic** | Plan 의 "In Scope" 그대로. firmware 에 heating 상태 2변수 추가 + D3 핸들러 확장, backend 두 지점 순서 뒤집기, frontend ShadingCard 즉시 경로 | 3 레이어, ~40 lines | Low | **✅ 선택** |

**Rationale**: 증상 직결 원인을 모두 덮으면서, HW 제약 계약을 firmware 에 국소화. 각 레이어 수정 독립성이 높아 3팀 병렬 Do 에 적합.

---

## 3. Detailed Design — Layer-by-Layer

### 3.1 Firmware (`FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino`)

#### 3.1.1 상태 변수 추가 (line ~48-57)

```diff
 // 액추에이터 상태
 bool fanOn = false;
 bool waterOn = false;
 bool lightOn = false;
 bool shadeOn = false;
+bool heatingOn = false;  // D3 버튼이 shade 와 함께 일괄 토글 (HW 계약)

 // 인터럽트용 플래그
 volatile bool fanPressed = false;
 volatile bool lightPressed = false;
 volatile bool shadePressed = false;
```

> **설계 메모**: `heatingPressed` 별도 플래그는 만들지 않는다. D3 인터럽트 1회 = `shadePressed=true` 만 세팅되고, `checkButtons()` 안에서 두 액추에이터를 동시 토글. 인터럽트 플래그를 하나로 유지해 "한 번의 물리 액션 = 하나의 논리 이벤트" 의미를 분명히 한다.

#### 3.1.2 `checkButtons()` shade 분기 교체 + `reportButton` shading payload 에 `on` 필드 추가

**설계 결정(업데이트)**: 초기 Design 에서는 firmware 가 `reportButton("heating", ...)` 을 **별도 이벤트**로 방출하는 안이었으나, backend `control_store.update_control_state` 가 `control_type in {ventilation, irrigation, lighting, shading}` 만 허용 → `"heating"` 은 `ValueError` → HTTP 500 (5s timeout 대기까지 겹쳐 오히려 느려짐). 따라서 firmware 는 shading 이벤트 **1개**만 방출하되, payload 에 `on` 필드를 포함시켜 프론트 ShadingCard 마스터 토글 상태(state.on)까지 일관되게 전파한다. heating 은 firmware 내부 상태(`heatingOn`)로만 유지하고, 현재 하드웨어상 LED 는 공유.

```diff
   if (shadePressed) {
     shadePressed = false;
-    shadeOn = !shadeOn;
+    shadeOn = !shadeOn;
+    heatingOn = shadeOn;  // D3 HW 계약: firmware 내부 상태 동기
     mirrorLeds();
     reportButton("shading", shadeOn);
     lastBtnMs = millis();
+    return;
   }
```

그리고 `reportButton` shading 분기 payload:

```diff
   } else if (strcmp(ct, "shading") == 0) {
     snprintf(state, sizeof(state),
-      "{\"shade_pct\":%d,\"insulation_pct\":0}",
-      on ? 100 : 0);
+      "{\"shade_pct\":%d,\"insulation_pct\":0,\"on\":%s}",
+      on ? 100 : 0, on ? "true" : "false");
   }
```

> **순서 중요**: `mirrorLeds()` 호출은 state 갱신 후. shading POST 1회로 HW 계약(shade+heating 동시 토글) 표현.

#### 3.1.3 `applyCommand()` heating case 추가 (line 254-260 뒤) — 미래 확장용

```diff
   } else if (strcmp(ct, "shading") == 0) {
     if (a.containsKey("shade_pct")) {
       shadeOn = (a["shade_pct"].as<int>() > 0);
     } else if (a.containsKey("active")) {
       shadeOn = a["active"].as<bool>();
     }
+  } else if (strcmp(ct, "heating") == 0) {
+    // D3 HW 계약상 shade 와 동기 상태이나, 서버 명령은 독립 수신 가능
+    if (a.containsKey("insulation_pct")) {
+      heatingOn = (a["insulation_pct"].as<int>() > 0);
+    } else if (a.containsKey("on")) {
+      heatingOn = a["on"].as<bool>();
+    } else if (a.containsKey("active")) {
+      heatingOn = a["active"].as<bool>();
+    }
   } else if (strcmp(ct, "irrigation") == 0) {
```

> **메모**: LED 는 기존 `LED_SHADE (D8)` 하나로 두 액추에이터 공유 표시. `mirrorLeds()` 는 변경 없음. `sendToServer()` 의 디버그 로그에 `heating=%d` 추가는 optional(토큰 여유 있으면).

#### 3.1.4 배포

- 빌드: Arduino IDE / PlatformIO (ESP8266 core 3.x)
- 재플래시: USB 우선 (OTA 미구성). 사용자 승인 후 단일 다운타임 창 (< 2분)
- 부팅 로그로 `[BOOT] polling mode ready` 확인

### 3.2 Backend (`iot_relay_server/app/ai_agent.py`)

#### 3.2.1 rule 분기 순서 교정 (line 544-547)

```diff
     for d in rule_decisions:
         d["duration_ms"] = rule_duration_ms
-        _broadcast("ai_decision", d)
-        await _persist_decision(d)
+        await _persist_decision(d)
+        _broadcast("ai_decision", d)
```

#### 3.2.2 `override_control()` 순서 교정 (line 602-604)

```diff
     # SSE broadcast + DB persist
     from app.store import _broadcast
-    _broadcast("ai_decision", decision)
-    await _persist_decision(decision)
+    await _persist_decision(decision)
+    _broadcast("ai_decision", decision)
```

#### 3.2.3 tool 분기 (line 386-387) — 변경 없음, 참조용

```python
await _persist_decision(d)
_broadcast_store("ai_decision", d)
```

위 패턴을 나머지 두 지점도 따르게 맞추는 것이 이번 수정의 본질.

#### 3.2.4 rule 분기 `reasoning_trace` 처리 결정

- 현재 rule_decisions 는 `_record_decision()` 출력이며, `tool_calls`, `reasoning_trace` 필드가 **비어 있거나 없음**.
- Bridge UPSERT (`ai_agent_bridge.py:331`) 가 `ON CONFLICT (id) DO NOTHING` 이므로, persist 가 먼저 일어나면 정상 row 가 박히고 이후 broadcast 가 동일 id 로 나가도 Bridge 가 덮어쓰지 않아도 문제 없음(이미 정상 persist 됨).
- 즉, **순서만 뒤집어도 본 문제 해결 가능**. rule row 에 `reasoning_trace: []` 를 명시 주입하는 추가 변경은 out-of-scope 로 보류.

### 3.3 Frontend

#### 3.3.1 `ManualControlPanel.tsx` — ShadingCard 마스터 토글 경로

> **현 상태 확인 필요**: 앞선 탐색 리포트상 `ShadingCard` 의 master toggle 이 `onMaster` prop 으로 `sendCommandImmediate` 혹은 `sendCommand` 중 하나를 받는다. 실제 assembly(카드에 전달하는 함수) 가 debounce 경로면 아래 교체, 이미 immediate 면 OFF 원자화만 수행.

변경 원칙:
- 마스터 토글 = `sendCommandImmediate('shading', payload)` 로 명시 지정
- OFF payload = `{ shade_pct: 0, insulation_pct: 0, on: false }` (단일 호출, 원자적)
- ON payload = 기존 복원 로직 유지 (archived `manual-control-onoff` 규약) + `on: true`

```tsx
// ShadingCard 마스터 토글 핸들러 (개념 예시)
const onMasterToggle = () => {
  if (state.on) {
    sendCommandImmediate('shading', {
      shade_pct: 0,
      insulation_pct: 0,
      on: false,
    });
  } else {
    const restored = lastKnownValues.current.shading ?? { shade_pct: 50, insulation_pct: 0 };
    sendCommandImmediate('shading', { ...restored, on: true });
  }
};
```

슬라이더(shade_pct, insulation_pct) 는 기존 300ms debounce (`sendCommand`) 유지. 마스터 토글만 즉시 경로.

#### 3.3.2 `useManualControl.ts` — race guard

`handleControlEvent` 에서 source='button' SSE 수신 시 해당 control_type 의 optimistic lock 을 즉시 해제 (5초 타임스탬프 가드 무시):

```ts
const handleControlEvent = useCallback((event: ControlEvent) => {
  const ct = event.control_type as keyof ManualControlState;

  // source='button' 은 항상 반영 (ESP8266 물리 버튼이 SSoT)
  if (event.source === 'button') {
    manualTimestamps.current[ct] = 0;  // optimistic lock 해제
    // ... state 즉시 갱신
    return;
  }

  const isAISource = ['rule', 'tool', 'ai'].includes(event.source);
  // ... 기존 로직
}, []);
```

#### 3.3.3 `handleControlEvent` 보정 — `on` 필드 derive 로직 추가

**Rationale**: `fetchState()` 에는 이미 `data.shading.on ?? data.shading.led_on ?? false` 정규화가 있으나, `handleControlEvent` 의 SSE 업데이트에는 동일 로직이 빠져있어 `on` 필드가 업데이트 되지 않은 채 이전 값 유지 → UI master toggle 이 "ON" 으로 남는 증상. 방어적 이중화로 payload 에 `on` 없으면 `led_on` 혹은 `active` 에서 derive.

```ts
const handleControlEvent = useCallback((event: ControlEvent) => {
  const ct = event.control_type as keyof ManualControlState;
  const isAISource = ['rule', 'tool', 'ai'].includes(event.source);
  const elapsed = Date.now() - (manualTimestamps.current[ct] || 0);
  if (isAISource && elapsed < 5000) return;

  // source='button' 은 SSoT → optimistic lock 즉시 해제
  if (event.source === 'button') manualTimestamps.current[ct] = 0;

  setControlState(prev => {
    if (!prev || !(ct in prev)) return prev;
    const incoming = event.state as Record<string, unknown>;
    const merged = { ...prev[ct], ...incoming, source: event.source, updated_at: event.timestamp };
    if (!('on' in incoming)) {
      merged.on = incoming.led_on ?? incoming.active ?? prev[ct].on;
    }
    return { ...prev, [ct]: merged };
  });
}, []);
```

heating 은 현재 backend 미지원이므로 별도 control_type 구독 불필요. 차광/보온 카드는 기존 `controlState.shading` 하나로 표시.

---

## 4. Data / API Contract

### 4.1 ESP8266 → Relay `/api/v1/control/report`

| control_type | payload | 트리거 |
|---|---|---|
| ventilation | `{active, fan_speed, window_open_pct}` | FAN 버튼 |
| lighting | `{on, brightness_pct}` | LIGHT 버튼 |
| shading | `{shade_pct, insulation_pct, on}` **(on 필드 신규)** | D3 버튼 (1회) |

> **heating 별도 control_type 은 backend 미지원**. D3 는 shading 하나만 방출하고, HW 계약(차광+보온 일괄 토글) 은 프론트 UI 가 shading state 하나로 표현(차광/보온 통합 카드).

### 4.2 Relay → Frontend SSE `ai_decision`

| 분기 | 경로 | broadcast 시점 |
|---|---|---|
| tool | line 386-387 | persist 후 ✅ |
| rule | line 546-547 | **persist 후 (수정)** |
| override | line 603-604 | **persist 후 (수정)** |

### 4.3 Frontend → Relay `/control`

| control_type | OFF payload | ON payload |
|---|---|---|
| shading | `{ shade_pct: 0, insulation_pct: 0, on: false }` (단일 호출) | `{ shade_pct: N, insulation_pct: M, on: true }` |

---

## 5. Test Plan

### 5.1 L1 — firmware 실장비 검증 (Manual)

| 시나리오 | 기대 |
|---|---|
| D3 버튼 1회 누름 | Serial 에 `[BTN] shading -> ON/OFF (HTTP 200)` 1회. 500 에러 없음 (heating POST 제거) |
| D3 10회 연속 토글 | shadeOn/heatingOn 내부 상태 매번 동기 전환 (Serial `[SENS] ...shade=X ...` 로 확인) |
| 대시보드에서 shading 변경 push | `applyCommand` 가 shadeOn 반영 |
| (확장성) 서버가 heating control_type 내려보내면 | `applyCommand` heating case 가 heatingOn 갱신 — 현재는 서버 경로 없음이라 미사용 |
| 서버 단절 30초 | watchdog 재부팅 후 polling 복구 (회귀 없음) |

### 5.2 L2 — backend unit/integration

| 시나리오 | 기대 |
|---|---|
| rule_decisions 중 1건이 emergency priority | `ai_agent_decisions` 에 row insert → 이후 SSE emit. DB 쿼리 순서 검증 로그 (`monotonic` ts 비교) |
| override_control 호출 | 동일 순서 |
| 회귀: tool 분기 | 기존 동작 그대로 (persist → broadcast) |

### 5.3 L3 — Playwright e2e (frontend)

```ts
test('D3 버튼 SSE 도착 시 차광/보온 동시 OFF 반영', async ({ page }) => {
  await page.goto('/iot/dashboard');
  // 사전: 차광/보온 ON 상태로 세팅
  await page.click('[data-testid=shading-master]');  // ON
  await expect(page.locator('[data-testid=shading-on]')).toBeVisible();

  // ESP8266 버튼 시뮬: SSE mock 에서 shading+heating 두 이벤트 주입
  await injectSSE({ control_type: 'shading', source: 'button', values: { on: false } });
  await injectSSE({ control_type: 'heating', source: 'button', values: { on: false } });

  // 5초 내 두 카드 모두 OFF
  await expect(page.locator('[data-testid=shading-off]')).toBeVisible({ timeout: 5000 });
  await expect(page.locator('[data-testid=heating-off]')).toBeVisible({ timeout: 5000 });
});
```

### 5.4 L4 (optional, Enterprise 범위 아님)

- 없음.

---

## 6. Rollout Plan

1. **Backend 먼저 배포**: ai_agent.py 순서 수정은 회귀 위험 낮고 ESP8266 재플래시 없이 가능. 현 운영 중단 없음.
2. **Frontend 다음**: 빌드 → `pnpm build` → 정적 배포. 사용자 새로고침으로 반영.
3. **Firmware 마지막**: 사용자와 재플래시 타이밍 조율 (실시간 측정 2분 단절). USB 플래시 → `[BOOT]` 로그 확인 → 수동 D3 10회 검증.
4. **Check 단계**: 위 L1/L2/L3 순서대로 실행. matchRate ≥ 90% 목표.

---

## 7. Risks & Mitigations (Design-level)

| Risk | Mitigation |
|---|---|
| heatingOn 상태가 재부팅 시 초기값(false) 로 돌아감 | ESP8266 은 원래 재부팅 시 모두 false. 정책 일관 — 서버 polling 이 곧 복원 |
| backend 순서 변경으로 broadcast 실패해도 persist 는 성공 | `_broadcast` 는 sync 함수, 실패해도 예외 흡수. persist 먼저이므로 데이터 손실 없음 |
| frontend immediate 경로가 사용자 더블클릭에서 2회 POST | 기존 조명/환기와 동일 UX, 추가 rate limit 불필요 |

---

## 8. Implementation Guide

### 8.1 Module Map (3 팀 병렬)

| Module | Team | Files | Est. Diff |
|---|---|---|---|
| module-fw | firmware-team | `FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino` | +8 -2 |
| module-be | backend-team | `iot_relay_server/app/ai_agent.py` | +4 -4 |
| module-fe | frontend-team | `FarmOS/frontend/src/modules/iot/ManualControlPanel.tsx` + `FarmOS/frontend/src/hooks/useManualControl.ts` | +20 -6 (추정) |

### 8.2 Recommended Session Plan

- **Session 1** (병렬 가능): firmware-team 이 `.ino` 수정 + 로컬 빌드 / backend-team 이 `ai_agent.py` 두 지점 patch + 단위 테스트 초안 / frontend-team 이 ShadingCard + useManualControl 수정
- **Session 2**: backend → frontend → firmware 순 배포 및 L1/L2/L3 검증
- **Session 3**: gap-detector 로 Check → 필요시 iterate

### 8.3 Session Guide (per-team)

- **firmware-team** 진입 시 `--scope module-fw`, 참고 섹션 §3.1
- **backend-team** 진입 시 `--scope module-be`, 참고 섹션 §3.2
- **frontend-team** 진입 시 `--scope module-fe`, 참고 섹션 §3.3

---
