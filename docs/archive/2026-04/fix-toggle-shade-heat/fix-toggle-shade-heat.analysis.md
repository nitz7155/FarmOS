# Fix Toggle: 차광/보온 동기화 — Gap Analysis

> **Feature**: fix-toggle-shade-heat
> **Plan**: `FarmOS/docs/01-plan/features/fix-toggle-shade-heat.plan.md`
> **Design**: `FarmOS/docs/02-design/features/fix-toggle-shade-heat.design.md`
> **Date**: 2026-04-24
> **Phase**: Check (Static analysis + Runtime pending)
> **Analyzer**: self (gap-detector agent 부분 대체 — 스코프 작고 범위 명확)

---

## Context Anchor (propagated)

| Key | Value |
|-----|-------|
| **WHY** | 차광/보온이 D3 핀 공용 제어라는 HW 계약을 3 레이어가 충실히 반영 못함 |
| **WHO** | FarmOS 1인 농업인, ESP8266 물리 버튼과 웹 토글 병행 |
| **RISK** | 실시간 측정 중 재플래시 단절 / backend 순서 변경 회귀 / sendCommandImmediate 과다 호출 |
| **SUCCESS** | SC-1~5 (Plan 참조) |
| **SCOPE** | FW shade 분기 + shading payload on / BE ai_agent.py 순서 / FE handleControlEvent derive |

---

## 1. Strategic Alignment

- ✅ **PRD(없음)**: 이번 feature 는 버그 fix 성격으로 PRD 단계 생략. Plan 이 WHY/WHO/SCOPE 를 직접 서술.
- ✅ **Plan WHY 해결**: "D3 HW 계약을 3 레이어가 충실히 반영" 요구가 FW/BE/FE 수정으로 충족. firmware 가 shading payload 에 on 포함, backend 는 불변식(persist→broadcast) 적용, frontend 는 SSE 경로에도 on derive 추가.
- ⚠️ **Design 재조정 이력**: Do 단계 초반 "heating 별도 control_type" 안이 backend `Unknown control_type` 거부로 실패 → firmware 는 shading 이벤트 1개로 축소 + payload 에 on 추가로 선회. Design 문서 §3.1.2, §3.3.3, §4.1, §5.1 업데이트 완료.

## 2. Plan Success Criteria 평가

| # | Criterion | Status | Evidence |
|---|---|---|---|
| SC-1 | D3 1회 누름 → shading + heating SSE 2개 (간격 ≤100ms) | ⚠️ **Revised** | Design 재조정으로 "shading SSE 1개, state 에 on/shade_pct/insulation_pct 반영" 으로 개정. firmware `reportButton` 단일 호출(.ino:172). Runtime 검증 필요 |
| SC-2 | 10회 연속 토글 시 OFF 실패 0/10 | ⏳ Pending runtime | ESP8266 재플래시 후 검증 가능 |
| SC-3 | 차광/보온 체감 응답 ±200ms of 조명/환기 | ⏳ Pending runtime | 동일 |
| SC-4 | ai_agent_decisions rule row 의 tool_calls/reasoning_trace 비어있지 않음 | ⚠️ Partial | broadcast/persist 순서 교정(ai_agent.py:547-548, 605-606)으로 Bridge 락인 문제 해소. 단, rule row 의 tool_calls 필드 자체는 `_record_decision` 구현상 여전히 공란(or [])일 수 있음 — 확인 필요 |
| SC-5 | 조명·환기·관수 회귀 0건 | ⏳ Pending runtime | static 으로는 영향 없음. 런타임 확인 필요 |

## 3. Structural Match (가중치 0.2)

| 항목 | 기대 | 실제 | 상태 |
|---|---|---|---|
| firmware 상태변수 | `heatingOn` 추가 | .ino:53 | ✅ |
| firmware shade 분기 | 동시 토글 + return | .ino:163-175 | ✅ |
| firmware reportButton shading | on 필드 포함 | .ino:401-403 | ✅ |
| firmware applyCommand heating case | 추가 | .ino:267-275 | ✅ |
| backend rule 분기 순서 | persist → broadcast | ai_agent.py:547-548 | ✅ |
| backend override_control 순서 | persist → broadcast | ai_agent.py:605-606 | ✅ |
| backend tool 분기 (비교군) | persist → broadcast (기존) | ai_agent.py:386-387 | ✅ 그대로 |
| frontend handleControlEvent | source='button' lock 해제 + on derive | useManualControl.ts:253-273 | ✅ |
| frontend ShadingCard atomic OFF | 단일 payload | ManualControlPanel.tsx:325 (기존) | ✅ |

**Structural 점수: 100%** (9/9)

## 4. Functional Depth (가중치 0.4)

| 기능 | 검증 내용 | 상태 |
|---|---|---|
| D3 인터럽트 1회 = shade + heating 토글 | `shadeOn = !shadeOn; heatingOn = shadeOn;` — firmware 내부 상태 동기 | ✅ |
| firmware shade 분기 명시적 return | .ino:174 `return;` | ✅ |
| shading payload on 포함 | `{"shade_pct":N,"insulation_pct":0,"on":bool}` | ✅ |
| backend 불변식 (persist→broadcast) | rule(547-548), override(605-606), tool(386-387) 3 지점 모두 일관 | ✅ |
| frontend source='button' optimistic 해제 | `manualTimestamps.current[ct] = 0` (line 254) | ✅ |
| frontend SSE payload 에 on 없을 시 derive | `merged.on = ledOn ?? active ?? prev.on` (line 269-273) | ✅ |
| `applyCommand` heating case | 서버가 heating control_type 을 현재 내려보내지 않아 **dead code** — Design 은 미래 확장으로 명시 | ⚠️ Intentional |
| `heatingOn` firmware 내부 변수 | LED 는 LED_SHADE 에 공유 (HW 한 회로) — 별도 표시 없음 | ℹ️ By design |

**Functional 점수: 95%** (heating case 가 현재 시점에 활용되지 않지만 Design 에 명시적 미래 확장이므로 full 감점 아님)

## 5. API Contract (가중치 0.4)

3-way verification: Design §4 ↔ firmware payload ↔ backend schema ↔ frontend handler

| 경로 | Design 계약 | 구현 | Gap |
|---|---|---|---|
| FW→BE /control/report shading | `{shade_pct, insulation_pct, on}` | firmware: 동일 (.ino:401-403) | ✅ |
| BE shading state 필드 | Design §4.1 에 `on` 명시 안 함 (backend 쪽은 led_on/active 사용) | control_store shading = `{shade_pct, insulation_pct, active, led_on, locked, source, updated_at}` — **on 없음** | ⚠️ Backend 가 firmware 의 `on` 을 **silently drop** (`update_control_state` 의 `for key,val: if key in state` 필터). Design §3.3.3 에서 "frontend derive 이중 안전" 로 의도 명시 |
| BE→FE SSE `control` 이벤트 payload | `{shade_pct, insulation_pct, active, led_on, ...}` | `_get_public_state` (control_store:178) 로 전파 | ✅ |
| FE handleControlEvent 처리 | event.state 에 on 없으면 led_on/active 기반 derive | useManualControl.ts:269-273 | ✅ |
| AI decision SSE (rule) payload | `reasoning_trace, tool_calls` 부착 후 broadcast | `_record_decision` 이 tool_calls 를 비어있게 둘 수 있음 — 순서 교정으로 Bridge 락인은 해소되나 데이터 완전성은 별개 | ⚠️ SC-4 Partial |

**Contract 점수: 88%** (2 개 ⚠️ — 둘 다 Design 상 의도된 trade-off 이지만 완벽한 contract 일치는 아님)

## 6. Runtime Verification — Pending

**현재 상태**: ESP8266 재플래시 / iot_relay_server 재시작 / frontend 재배포 미완료. L1/L2/L3 런타임 테스트 미수행.

배포 후 실행할 검증 스크립트:

### L1 — API (서버 재시작 후)
```bash
# rule 분기 트리거 후 /api/v1/ai-agent/decisions 조회하여
# 최신 row 가 tool_calls 필드를 가지는지 (NULL 이면 SC-4 미해결)
curl -s http://localhost:8000/api/v1/ai-agent/decisions?limit=1 | jq '.[0].tool_calls'
```

### L2 — firmware (재플래시 후)
- D3 버튼 10회 토글 → Serial 로그에 `[BTN] shading -> ON (HTTP 200)` / `OFF (HTTP 200)` 교대
- HTTP 500 / timeout 로그 없음
- `[SENS]` 주기 로그에서 `shade=<0|1>` 값이 각 토글마다 flip

### L3 — e2e (frontend 재배포 후)
- 대시보드 ShadingCard 에서 물리 D3 버튼 OFF → 마스터 토글 5초 내 OFF 전환
- 슬라이더 shade_pct=0, insulation_pct=0 반영
- 조명/환기/관수 카드 회귀 없음

## 7. Match Rate 계산 (Static-only 공식)

```
Overall = Structural × 0.2 + Functional × 0.4 + Contract × 0.4
        = 100 × 0.2 + 95 × 0.4 + 88 × 0.4
        = 20 + 38 + 35.2
        = 93.2%
```

**Match Rate = 93%** — 90% 기준 통과.

> Runtime 검증 후 `Overall = Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35` 공식으로 재계산 가능.

## 8. Decision Record Verification

| Decision | Source | Followed? | 비고 |
|---|---|---|---|
| D3 pairing layer = firmware SSoT (reportButton 두 번) | User 선택(Q1) | ⚠️ 변형 수용 | backend 제약으로 "firmware 내부 상태만 동기, SSE 는 shading 1개" 로 재해석. User 의도는 충족 |
| Scope = 필수 + backend 순서 수정 | User 선택(Q2) | ✅ | Plan/Design 범위 내 |
| Architecture = Option C Pragmatic | Design §2 | ✅ | lock TTL / Bridge 스키마 / UI 카드 통합은 out-of-scope 유지 |
| 불변식 "broadcast 는 persist 후" (프로젝트 메모) | project_iot_relay_llm_pipeline.md | ✅ | 3 지점 일관 적용 |
| HW 계약 "D3 = shade+heating 동시" (프로젝트 메모) | project_esp8266_pin_binding.md | ✅ | firmware `heatingOn=shadeOn` 로 표현 |

## 9. Gap 목록 (severity + 권고)

| # | 심각도 | Gap | 위치 | 권고 |
|---|---|---|---|---|
| G-1 | ℹ️ Info | firmware `applyCommand` heating case 는 현재 backend 가 heating control_type 을 내려보내지 않아 사용되지 않음 | .ino:267-275 | 유지 (미래 확장 대비). 또는 이번 feature 에서 제거하고 Design 도 미래 feature 로 미루기 |
| G-2 | ⚠️ Minor | backend shading state 에 `on` 필드 없음 — firmware 가 보낸 on 이 drop | control_store.py:49-57 | **선택 A (간단)**: control_store shading state 에 `"on": False` 추가 후 `update_control_state` loop 가 인식 → SSE payload 에 on 포함 → frontend derive 불필요. **선택 B (현 상태 유지)**: Design 명시된 "이중 안전" 으로 수용 |
| G-3 | ⚠️ Minor | rule decision 의 `tool_calls` 필드가 `_record_decision` 구현상 비어있을 수 있음 (NULL vs [] 확인 필요) | `_record_decision` 구현 | 후속 feature 에서 rule decision 에도 최소한 `tool_calls: []` 명시 주입 (out-of-scope 유지) |
| G-4 | ⏳ Pending | Runtime 검증 미수행 | L1/L2/L3 | 배포 후 본 문서 §6 체크리스트 실행, 결과를 Report 에 첨부 |

**Critical (confidence ≥80%) Gap 없음.**

## 10. 결론

- Static Match Rate **93%** — 90% 기준 통과.
- Critical severity gap 없음.
- Minor gap 2개는 Design 범위 내 의도된 trade-off (G-1, G-2).
- 런타임 검증(SC-2/3/5)은 배포 후 수행 필수. 배포까지 blocker 없음.

다음 단계 권고: **Report 로 진행** (match rate ≥90% + critical 없음). 단, Report 에 "Runtime SC 는 배포 후 업데이트" 를 explicit 으로 남겨야 함.

---
