# Fix Toggle: 차광/보온 동기화 — Completion Report

> **Feature**: fix-toggle-shade-heat
> **Period**: 2026-04-24 (Plan → Design → Do → Check, 단일 세션)
> **Match Rate (Static)**: **93%** (target ≥90% ✅)
> **Runtime Verification**: Pending deployment (ESP8266 재플래시 + 서버 재시작 + frontend 재배포 후 수행)
> **PDCA Phase**: Report (pre-archive)

---

## Executive Summary

| Perspective | Content |
|---|---|
| **Problem** | ESP8266 D3 버튼 1개가 차광막 + 보온커튼을 일괄 제어(HW 제약)하는데, firmware `reportButton` shading payload 에 `on` 필드가 빠져 있고 backend `control_store` shading state 에도 `on` 필드가 없어 → frontend `state.on` 이 SSE 경로로 업데이트되지 않아 "보온 OFF 안 돌아옴" 체감. 추가로 backend rule 분기에서 broadcast↔persist 순서가 역전되어 Bridge UPSERT 가 빈 tool_calls row 를 락인할 수 있는 불변식 위반 잔존. |
| **Solution** | 3 레이어 소규모 수정: (1) firmware shade 분기에서 `shadeOn`/`heatingOn` 동시 토글 + `return;` + shading payload 에 `"on":bool` 추가. (2) backend `ai_agent.py` 두 지점(line 547-548, 605-606)에서 `persist → broadcast` 순서로 교정. (3) frontend `handleControlEvent` 에 `source='button'` optimistic lock 즉시 해제 + payload 에 `on` 없을 때 `led_on`/`active` 기반 derive 이중 안전장치. |
| **Function/UX Effect** | D3 버튼 1회 누름 = 대시보드 차광/보온 카드 마스터 토글이 즉시 반응(배포 후 검증). heating reportButton 중복 POST 제거로 버튼당 HTTP 호출 1회 유지. rule 엔진 SSE 가 persist 완료 후 broadcast 되어 Bridge 데이터 완전성 확보. |
| **Core Value** | 하드웨어 제약(핀 부족으로 D3 공용)을 그대로 유지한 채 3 레이어 SSoT 일관성 복원. 야간 농작물 보호(차광/보온)에 대한 현장 운용자 신뢰 회복. 불변식(persist 후 broadcast) 을 코드에 정착시켜 이후 관련 feature 의 회귀 방지. |

### Value Delivered (Post-Check)

| 지표 | Before | After (Static) | After (Runtime pending) |
|---|---|---|---|
| firmware shading payload 의 `on` 필드 | 없음 | 포함 (.ino:401-403) | - |
| backend broadcast/persist 불변식 위반 지점 | 2 곳 | **0 곳** (ai_agent.py:547-548, 605-606) | - |
| frontend SSE 경로의 `on` derive | 없음 | `led_on/active` fallback (useManualControl.ts:269-273) | - |
| 체감 "보온 OFF 안 돌아옴" | 빈번 | 해결(이론) | 재플래시 후 검증 |
| D3 버튼당 HTTP POST 수 | 1회 | 1회 (heating 중복 제거) | - |
| Match Rate | N/A | 93% Static | runtime 합산 재계산 가능 |

---

## 1. Context Anchor (final)

| Key | Value |
|-----|-------|
| **WHY** | 차광/보온이 D3 핀 공용 제어라는 HW 계약을 3 레이어가 충실히 반영 못함 |
| **WHO** | FarmOS 1인 농업인, ESP8266 물리 버튼과 웹 토글 병행 |
| **RISK** | 실시간 측정 중 재플래시 단절(배포 시) / backend 순서 변경 회귀 / sendCommandImmediate 과다 호출 |
| **SUCCESS** | SC-1~5 (§4 참조) |
| **SCOPE** | FW shade 분기 + shading payload on / BE ai_agent.py 두 지점 / FE handleControlEvent derive. **Out-of-scope**: lock TTL, Bridge UPSERT 스키마, UI 카드 통합, heating 전용 GPIO |

---

## 2. PDCA Journey

| Phase | 산출물 | 주요 결정 |
|---|---|---|
| Plan | `01-plan/features/fix-toggle-shade-heat.plan.md` | 3 레이어 root cause 분석, SC-1~5, 권장 scope 확정 |
| Design | `02-design/features/fix-toggle-shade-heat.design.md` | Option C Pragmatic 선택, Do 중 "heating 별도 control_type" 안이 backend 미지원 확인되어 "shading payload 에 on 추가" 로 재조정 |
| Do | 3 파일 수정 (firmware, ai_agent.py, useManualControl.ts) + Design 문서 실시간 업데이트 | firmware-team/backend-team/frontend-team 3 팀 병렬 작업 |
| Check | `03-analysis/fix-toggle-shade-heat.analysis.md` | Static Match Rate 93%, Critical gap 0, Minor gap 4 (모두 의도된 trade-off or pending) |

---

## 3. Key Decisions & Outcomes (Decision Record)

| Decision | Phase | 배경 | 결과 |
|---|---|---|---|
| D3 HW 제약 표현 위치 = firmware SSoT | Plan (user Q1) | 핀 부족으로 차광+보온 일괄 제어 | firmware 내부 상태는 `shadeOn`/`heatingOn` 동기. SSE 계약은 shading 1개 + `on` 필드로 단순화(Do 재조정) |
| Architecture = Option C Pragmatic | Design | Plan 범위와 일치 | 3 파일, ~30 lines 변경. YAGNI 원칙 준수 |
| Out-of-scope 유지: lock TTL, Bridge 스키마, UI 카드 통합 | Design | 범위 확장 위험 vs 증상 직결 원인 집중 | Minor gap 4개 중 3개가 이들 범주. 의도대로 |
| heating 별도 control_type 안 → shading payload on 필드 안 | Do (실구현 중) | backend `update_control_state` 가 Unknown control_type 거부 | firmware reportButton heating 호출 제거, shading payload 에 `on` 추가. Design 문서 §3.1.2/§3.3.3/§4.1 동기 업데이트 |
| G-2 (backend shading state 에 `on` 필드 없음) 수용 | Check (user) | 10줄 수준 추가 수정 가능하나 frontend 이중 derive 로 방어 중 | 현 상태 유지, Report 에 명시 |

---

## 4. Plan Success Criteria — Final Status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| SC-1 | D3 1회 누름 → shading + heating SSE 2개 (간격 ≤100ms) | ⚠️ **Revised** | Design 재조정으로 "shading SSE 1개 + state 완전 반영" 으로 개정. firmware 구현 일치(.ino:172). Runtime 검증 필요 |
| SC-2 | 10회 연속 토글 시 OFF 실패 0/10 | ⏳ Pending runtime | ESP8266 재플래시 후 검증 |
| SC-3 | 차광/보온 체감 응답 ±200ms of 조명/환기 | ⏳ Pending runtime | 동일 |
| SC-4 | ai_agent_decisions rule row 의 tool_calls/reasoning_trace 비어있지 않음 | ⚠️ Partial | 순서 교정으로 Bridge 락인 해소. `_record_decision` 이 tool_calls 필드를 어떻게 채우는지는 별개 이슈 (out-of-scope) |
| SC-5 | 조명·환기·관수 회귀 0건 | ⏳ Pending runtime | static 으로는 영향 없음 |

**현재 Met 비율**: 0/5 Met (Runtime 검증 대기). Revised/Partial 1/5, Pending runtime 3/5.
**배포 후 예상**: SC-2, SC-3, SC-5 통과 가능성 높음.

---

## 5. Changed Files

| 파일 | Lines | 변경 요약 |
|---|---|---|
| `FarmOS/DH11_KY018_WiFi/DH11_KY018_WiFi.ino` | +14 / -3 | `heatingOn` 추가, shade 분기 확장(동시 토글 + return), shading payload 에 `on`, applyCommand heating case |
| `iot_relay_server/app/ai_agent.py` | +4 / -4 | line 547-548 / 605-606 순서 교정 |
| `FarmOS/frontend/src/hooks/useManualControl.ts` | +21 / -4 | handleControlEvent 에 source='button' lock 해제 + on derive |

**총 변경**: +39 / -11 (3 파일)

### 관련 문서 업데이트
- `02-design/features/fix-toggle-shade-heat.design.md` §3.1.2, §3.3.3, §4.1, §5.1 — Do 단계 재조정 반영

### Out-of-scope (변경 없음)
- `control_store.py` (shading state 에 `on` 추가 안 함 — G-2 수용)
- `ai_agent_bridge.py` (UPSERT 스키마 변경 안 함)
- `ManualControlPanel.tsx` (UI 카드 통합 안 함, ShadingCard atomic OFF 는 이미 기존 구현)

---

## 6. Deployment Checklist

배포 순서 (Design §6 rollout plan 재확인):

- [ ] **Backend** (`iot_relay_server`) 재시작
  - Docker: `docker compose -f iot_relay_server/docker-compose.yml restart`
  - 무중단 가능 (기존 DB 스키마 변경 없음)
- [ ] **Frontend** 빌드 + 배포
  - `cd FarmOS/frontend && pnpm build` → vercel 또는 정적 호스팅 업로드
  - 사용자 새로고침 필요
- [ ] **Firmware** USB 재플래시 (~2분 단절)
  - Arduino IDE 로 `DH11_KY018_WiFi.ino` 빌드 → 업로드
  - Serial 로 `[BOOT] polling mode ready` 확인

---

## 7. Runtime Verification Plan (post-deploy)

### L1 — API 검증 (backend 재시작 후)
```bash
# rule 엔진 트리거 후 최신 decision row 의 tool_calls 확인
curl -s http://localhost:8000/api/v1/ai-agent/decisions?limit=1 | jq '.[0] | {control_type, source, tool_calls}'
```

### L2 — firmware 실장비 (재플래시 후)
- D3 버튼 10회 토글 → Serial 로그:
  - `[BTN] shading -> ON (HTTP 200)` / `OFF (HTTP 200)` 교대
  - `[BTN] heating -> ...` 로그가 **없음** 확인 (중복 POST 제거 검증)
  - HTTP 500 / timeout 없음

### L3 — e2e 대시보드 (frontend 재배포 후)
- D3 버튼 OFF → ShadingCard 마스터 토글이 5초 내 OFF 로 전환
- 슬라이더 shade_pct=0, insulation_pct=0 반영
- 조명/환기/관수 회귀 없음

### 검증 결과 기록 방법
배포 후 본 Report §7 밑에 `### 7.x Runtime Results (YYYY-MM-DD)` 절을 추가하여 L1/L2/L3 결과 기재 → match rate 재계산 (runtime 가중치 0.35 포함).

---

## 8. Learnings (for future PDCA)

1. **Design Gap 조기 발견은 Do 단계에서도 합법적**. 이번 건은 Do 시작 5분만에 backend `update_control_state` 시그니처를 읽고 "heating 별도 control_type" 안이 불가능함을 발견 → Design 문서를 즉시 업데이트하고 구현 방향 전환. 미리 완벽한 Design 에 집착하기보다 "구현 단계의 발견을 Design 에 역반영" 하는 루프가 더 빠른 경우가 있음.

2. **SSoT 의 이중화는 의도적 선택일 수 있다**. firmware payload 의 `on` 과 frontend derive 로직은 "같은 정보를 두 경로로 보내는" 중복이지만, backend 가 drop 하는 상황에서 방어적 이중화. Design 문서에 "왜 중복인지" 를 명시하면 미래의 리팩토러가 이유 없이 한쪽 제거 안 함.

3. **사용자가 말한 "느림" ≠ "지연" 인 경우가 많다**. 이번 사례는 UI 업데이트 누락이 "반응 느림" 으로 체감됨. Profiling 에 앞서 "사용자가 실제로 확인하는 신호" 부터 검증하는 순서가 중요.

4. **Agent Teams 3팀 병렬 vs 단일 에이전트 직접 수정의 trade-off**. 이번 규모(~30 lines 3 파일) 는 단일 에이전트 직접 수정이 오케스트레이션 오버헤드 없이 빠름. 10명 이상 기여하거나 파일당 100+ lines 일 때 팀 오케스트레이션 value 가 커짐.

---

## 9. Post-Report Actions

### 9.1 즉시
- 배포 (Backend → Frontend → Firmware)
- Runtime L1/L2/L3 수행
- 본 Report §7 에 결과 추가

### 9.2 Archive 조건 충족 시
- 모든 SC 가 Met (또는 합의된 Deferred) 로 마무리되면 `/pdca archive fix-toggle-shade-heat --summary` 로 아카이브
- 관련 Plan/Design/Analysis/Report 를 `docs/archive/2026-04/fix-toggle-shade-heat/` 로 이동

### 9.3 후속 후보 (우선순위 낮음)
- **G-2 대응 (소규모)**: `control_store.py` shading state 에 `"on": False` 추가 → contract 완결. 별도 micro-feature 로 묶을 가치 있음.
- **G-3 대응 (중규모)**: `_record_decision` 이 rule decision 에도 `tool_calls: []`, `reasoning_trace: []` 명시 주입하도록 보정. Bridge UPSERT 의 데이터 완전성 최종화.
- **스케줄 가능한 점검**: 배포 2주 뒤 실제 운영 데이터로 `ai_agent_decisions` 테이블의 rule row tool_calls 충실도 점검 + D3 버튼 이벤트 로그에서 OFF 실패율 측정. `/schedule` 로 background 에이전트 걸어둘 수 있음.

---

## 10. Summary Card

```
Feature:        fix-toggle-shade-heat
Status:         Report (Check 93% Static, Runtime pending)
Duration:       ~4h (plan 0.5h + design 0.5h + do 2h + check 0.5h + report 0.5h)
Files Changed:  3 (+39 / -11)
Docs Produced:  Plan, Design, Analysis, Report
Critical Gaps:  0
Minor Gaps:     4 (3 by-design, 1 runtime-pending)
Decisions:      5 logged
```

---
