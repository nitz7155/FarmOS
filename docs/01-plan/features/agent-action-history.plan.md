# AI Agent Action History (IoT Relay → FarmOS Postgres) Planning Document

> **Summary**: N100 IoT Relay 에서 발생하는 AI Agent decision 을 SSE Bridge 로 FarmOS PostgreSQL 에 원본 미러 + 일별/시간별 요약으로 적재하고, 대시보드에서 상세보기·더보기(페이지네이션)·요약 카드를 제공한다.
>
> **Project**: FarmOS - agent-action-history
> **Version**: 0.1.0
> **Author**: clover0309
> **Date**: 2026-04-20
> **Status**: Draft
> **Prerequisites**: iot-postgres-migration 완료(로컬 BE 3 테이블 + Relay 패치 스펙), Relay `/ai-agent/decisions`·`/ai-agent/stream`(SSE) 동작, 프론트 `useAIAgent` 훅 존재

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | AI Agent 판단 이력이 N100 Relay 메모리(최대 20건)에만 존재하여 재시작 시 증발한다. 프론트는 `decisions?limit=20` 외에 상세보기/더보기 수단이 없어 "AI 가 무엇을 어떻게 판단했는가"의 추적 가능성이 사실상 0 이다. |
| **Solution** | FarmOS 로컬 BE 에 Bridge Worker 를 두어 Relay 의 `ai_decision` SSE 스트림을 상시 구독해 PostgreSQL 에 **원본 미러(최근 30 일)** 와 **일별·시간별 요약** 테이블로 적재한다. 프론트는 FarmOS BE 의 3 개 신규 엔드포인트(요약 / 목록 pagination / 단건 상세)를 호출하고, AIAgentPanel 에 "더보기" 무한 스크롤과 "상세보기" 모달을 추가한다. |
| **Function/UX Effect** | 대시보드에서 오늘/7 일/30 일 집계 카드 + 타임라인 + 한 건별 상세(before/after action JSON, tool_calls trace, 당시 센서 스냅샷, priority/source/reason/duration)를 확인할 수 있다. 서버 재시작 후에도 이력이 유지된다. |
| **Core Value** | AI Agent 의사결정의 **추적 가능성 + 영속성 + 설명 가능성** 확보. 운영자가 AI 판단을 감사·검증할 수 있고, 이후 RAG·파인튜닝 데이터셋의 기반이 된다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | Relay 메모리에만 있는 AI decisions 가 재시작 시 휘발되고 20 건 제한으로 상세 추적이 불가능하다. FarmOS 는 AI 활동에 대한 영속 기록·요약·감사 채널이 없다. |
| **WHO** | 김사과(Primary persona, 대시보드에서 AI 행동 확인·감사), 운영자/관리자(이력 조회·분쟁 확인), AI Agent 자신(과거 판단 회고용 RAG 컨텍스트). |
| **RISK** | (R1) SSE Bridge Worker 가 Relay 재시작/네트워크 단절 시 decision 유실 — cursor + 기동 시 backfill 로 대응. (R2) 양쪽 Postgres(Relay 전용 iot-postgres / FarmOS farmos) 간 중복 저장 — FarmOS 는 "미러 + 요약" 역할로 한정, 원본 single source 는 Relay. (R3) 고빈도 decision(초당 1 건 이상) 시 Worker 백프레셔 — batch commit + 요약 증분 갱신. (R4) 서버 조작 금지 원칙(N100) — Relay 코드는 patch-spec 문서만 제공, 본 레포 변경 금지. |
| **SUCCESS** | (SC-1) Relay 에서 발생한 모든 decision 이 FarmOS `ai_agent_decisions` 에 5 초 이내 insert 된다(p95). (SC-2) `/api/v1/ai-agent/activity/summary?range=today\|7d\|30d` 가 제어 타입별 건수·소스 분포·평균 duration 을 반환한다. (SC-3) 프론트 "더보기" 버튼 또는 무한 스크롤로 30 일치 이력까지 조회 가능하며 20 건 제한이 제거된다. (SC-4) 임의 decision 행 클릭 시 상세 모달에 reason / action JSON / tool_calls 순서·인자·결과 / 당시 센서 스냅샷 / priority / source / duration_ms 가 모두 표시된다. (SC-5) FarmOS BE 재시작 후에도 이전 세션 decisions 가 목록에 남아 있다. |
| **SCOPE** | IN: Relay 측 `iot_agent_decisions` 테이블 DDL + `/ai-agent/decisions?cursor=…` pagination API + `/ai-agent/decisions/{id}` 단건 상세 API (patch-spec 문서 연장), FarmOS BE `ai_agent_decisions` + `ai_agent_activity_daily` + `ai_agent_activity_hourly` 모델·마이그레이션, SSE Bridge background task, 3 개 API(`/summary`, `/decisions`, `/decisions/{id}`), FE 상세 모달·더보기(무한 스크롤) + 요약 카드. OUT: AI Agent 판단 로직 자체 수정, 모델 교체/비용 최적화, ESP8266 펌웨어, 알림 센터 통합, decision 데이터의 RAG 인덱싱, Relay 전체 아키텍처 리팩터링. |

---

## 1. Overview

### 1.1 Purpose

IoT 대시보드의 "AI Agent 제어" 패널에서 AI 가 수행한 **모든 행동(decision)** 을 영속 기록·요약·검색·상세 조회 가능하게 만든다. 현재는 Relay 메모리에 최대 20 건만 보관되고 "전체 N 건 보기" 버튼이 있어도 실제로는 fetch 된 20 건의 펼침만 제공한다.

### 1.2 Background

- `iot-postgres-migration` 작업으로 Relay 쪽도 PostgreSQL 전환이 진행 중이나, 해당 스펙에는 **AI Agent decisions 테이블이 없다** (센서/관수/알림 3 테이블만). Relay 의 AI 판단 결과는 여전히 `List[AIDecision]` 인메모리에만 있다.
- 프론트 `useAIAgent.ts` 는 `https://iot.lilpa.moe/api/v1/ai-agent/decisions?limit=20` 을 호출하고 SSE `ai_decision` 이벤트로 목록 최상단에 붙이는 구조다. 더 과거로 올라갈 수단이 없다.
- `AIAgentPanel.tsx` 의 "전체 N건 보기" 는 `decisions` state 의 slice(0, 5) vs 전체를 토글할 뿐이며, 20 건 이상 과거는 조회 불가다.
- 프로젝트 memory: **서버 조작 금지 (N100)** — Relay 측 코드는 본 레포에서 직접 수정할 수 없으므로 patch-spec 문서로 제공한다.

### 1.3 Related Documents

- `docs/iot-relay-server-postgres-patch.md` — Relay Postgres 전환 패치 스펙 (본 작업에서 `iot_agent_decisions` 테이블 추가 섹션 신설)
- `docs/01-plan/features/iot-postgres-migration.plan.md` — 선행 작업 (센서/관수/알림 3 테이블)
- `docs/02-design/features/iot-postgres-migration.design.md` — 선행 설계
- `docs/backend-architecture.md` — FarmOS BE 아키텍처
- `docs/database-schema.md` — DB 스키마 (본 작업에서 `ai_agent_*` 테이블 3 개 추가)
- `frontend/src/modules/iot/AIAgentPanel.tsx`, `frontend/src/hooks/useAIAgent.ts` — 프론트 진입점
- `frontend/src/types/index.ts` — `AIDecision`, `AIAgentStatus` 타입

---

## 2. Scope

### 2.1 In Scope

- [ ] **Relay patch-spec 확장** (`docs/iot-relay-server-postgres-patch.md` §10 신규)
  - `iot_agent_decisions` 테이블 DDL (id, timestamp, control_type, priority, source, reason, action JSONB, tool_calls JSONB, sensor_snapshot JSONB, duration_ms)
  - `GET /api/v1/ai-agent/decisions?cursor=…&limit=N` (keyset pagination)
  - `GET /api/v1/ai-agent/decisions/{id}` (단건 상세)
  - SSE `/api/v1/ai-agent/stream` 은 기존 유지(이미 존재), 메시지 payload 에 새 컬럼 반영
- [ ] **FarmOS BE 스키마/모델**
  - `backend/app/models/ai_agent.py` — `AiAgentDecision`, `AiAgentActivityDaily`, `AiAgentActivityHourly` 3 모델
  - `backend/app/core/database.py` 의 `init_db()` 경로로 `CREATE TABLE IF NOT EXISTS` 멱등 생성
- [ ] **SSE Bridge Worker**
  - `backend/app/services/ai_agent_bridge.py` — `httpx.AsyncClient.stream()` 으로 Relay SSE 상시 구독, 재접속 backoff, cursor 기반 backfill
  - `backend/app/main.py` lifespan 에 `asyncio.create_task()` 로 기동·종료 훅
  - 환경변수: `IOT_RELAY_BASE_URL`, `IOT_RELAY_API_KEY`, `AI_AGENT_BRIDGE_ENABLED`
- [ ] **FarmOS BE API 3 종** (`backend/app/api/ai_agent.py`)
  - `GET /api/v1/ai-agent/activity/summary?range=today|7d|30d`
  - `GET /api/v1/ai-agent/decisions?cursor=…&limit=20&control_type=&source=&priority=`
  - `GET /api/v1/ai-agent/decisions/{id}`
- [ ] **Frontend**
  - `useAIAgent` 수정 — 원격 base URL 을 FarmOS BE 로 교체, `fetchMore({cursor})` 추가, 상세 조회 `fetchDetail(id)`
  - `AIAgentPanel` — 요약 카드(오늘/7 일/30 일 탭), "더보기" 버튼 또는 IntersectionObserver 무한 스크롤, row click → 상세 모달
  - `AIDecisionDetailModal.tsx` 신규 — before/after 센서 스냅샷, action JSON tree view, tool_calls 순서 트레이스, copy-to-clipboard
- [ ] **Docs 갱신**
  - `docs/backend-architecture.md` §"AI Agent Bridge Worker" 섹션 추가
  - `docs/database-schema.md` 에 3 테이블 추가
  - `docs/iot-relay-server-plan.md` 보강

### 2.2 Out of Scope

- AI Agent 판단 로직/규칙 자체 수정 (priority/source 생성 규칙 불변)
- LLM 모델 교체·비용 최적화 (memory: 비용 우선 원칙은 유지하되 본 feature 대상 아님)
- ESP8266 펌웨어 (HTTP 계약 불변)
- 알림 센터·Slack·이메일 통합
- decision 데이터 RAG 인덱싱(임베딩) / 파인튜닝 파이프라인
- Manual Control 의 `locked` 정책 연계 (별도 feature)
- 기존 Relay 메모리 데이터의 DB 이관 (깨끗하게 시작)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Relay 에 `iot_agent_decisions` 테이블이 존재하고 decision 발생 시 insert 된다 (patch-spec 제공, 적용은 N100 에서 사용자) | High | Pending |
| FR-02 | Relay 가 `GET /ai-agent/decisions?cursor=…&limit=N` (keyset: `created_at < cursor`) 을 지원한다 | High | Pending |
| FR-03 | Relay 가 `GET /ai-agent/decisions/{id}` 로 단건 상세를 반환한다 (sensor_snapshot 포함) | High | Pending |
| FR-04 | FarmOS BE 에 `ai_agent_decisions` / `ai_agent_activity_daily` / `ai_agent_activity_hourly` 3 테이블이 생성된다 | High | Pending |
| FR-05 | FarmOS BE Bridge Worker 가 Relay SSE 를 구독해 수신 decision 을 `ai_agent_decisions` 에 insert 한다 | High | Pending |
| FR-06 | Worker 기동 시 FarmOS 가 보유한 가장 최근 `timestamp` 이후 Relay 이력을 backfill pull 한다 | High | Pending |
| FR-07 | Worker 는 각 decision insert 후 해당 날짜/시간 요약 행을 UPSERT 로 갱신한다 (count by type, count by source, avg duration) | High | Pending |
| FR-08 | `GET /api/v1/ai-agent/activity/summary?range=today\|7d\|30d` 가 집계 결과 JSON 을 반환한다 | High | Pending |
| FR-09 | `GET /api/v1/ai-agent/decisions?cursor=…` 가 keyset pagination 으로 20 건씩 반환한다 (필터: control_type, source, priority) | High | Pending |
| FR-10 | `GET /api/v1/ai-agent/decisions/{id}` 가 단건 상세를 반환한다 | High | Pending |
| FR-11 | 프론트 `useAIAgent` 훅이 `fetchMore(cursor)` 와 `fetchDetail(id)` 를 노출한다 | High | Pending |
| FR-12 | AIAgentPanel 에 오늘/7일/30일 요약 카드가 표시된다 | High | Pending |
| FR-13 | AIAgentPanel 의 목록이 "더보기" 또는 무한 스크롤로 과거 30 일까지 조회 가능하다 | High | Pending |
| FR-14 | 목록 row 클릭 시 상세 모달이 열리고 action JSON, tool_calls 순서, sensor_snapshot, duration_ms 가 모두 표시된다 | High | Pending |
| FR-15 | 상세 모달의 action JSON / tool_calls 는 복사 버튼을 제공한다 | Medium | Pending |
| FR-16 | Worker 가 네트워크 단절·Relay 재시작에서 지수 backoff(최대 60 초)로 자동 재접속한다 | Medium | Pending |
| FR-17 | FarmOS 측 미러는 30 일 TTL 로 정리된다 (야간 배치 또는 insert 시 확률 cleanup) | Low | Pending |
| FR-18 | 상세 모달에서 control_type / source / priority / 기간 필터로 재검색이 가능하다 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | decision 수신→`ai_agent_decisions` insert p95 < 5 s | `created_at_bridge - timestamp_relay` diff 로그 계측 |
| Performance | `/decisions?limit=20` p95 < 300 ms (30 일 range, 미러 30만 행 가정) | `timestamp` 인덱스 + keyset, `EXPLAIN ANALYZE` 검증 |
| Performance | `/activity/summary?range=30d` p95 < 150 ms | `ai_agent_activity_daily` 사전 집계 조회 |
| Reliability | Bridge Worker 가용성 99% — Relay 가 200 OK 로 복구되면 5 분 내 자동 재연결 | 재접속 시간 로그 |
| Consistency | FarmOS 미러 건수 = Relay 원본 건수(최근 30 일) ± 1 (드롭 허용) | 야간 배치 reconcile 쿼리 |
| Security | Relay 호출은 `X-API-Key` 헤더 포함. 프론트는 FarmOS BE 만 호출(세션 쿠키) | 코드 리뷰 + Network 패널 확인 |
| Accessibility | 상세 모달 WCAG 2.1 AA (Esc 닫기, focus trap, aria-labelledby) | axe-core 수동 확인 |
| Backward Compat | 기존 `AIDecision` 타입에 `id`, `sensor_snapshot?`, `duration_ms?` 선택 필드 추가 — 구 응답도 동작 | 프론트 타입 union + 옵셔널 렌더 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-14 (High) 모두 구현 완료
- [ ] Relay patch-spec 문서가 검토·머지됨 (실 적용은 N100 사용자 몫)
- [ ] FarmOS BE 재시작 후 이전 세션 decisions 가 목록에 남아 있음
- [ ] 프론트 상세 모달·더보기가 브라우저 수동 테스트 통과 (Chrome DevTools Network/Console 클린)
- [ ] Bridge Worker 이 Relay 강제 종료 → 재기동 시 자동 복구 (log 증빙)
- [ ] docs 3 건(`backend-architecture.md`, `database-schema.md`, Relay patch-spec) 갱신
- [ ] PDCA Gap 분석 Match Rate ≥ 90 %

### 4.2 Quality Criteria

- [ ] FarmOS BE unit test: Bridge 파서 / 요약 UPSERT / API 응답 shape
- [ ] Playwright E2E: 더보기·상세 모달 시나리오 1 개 이상
- [ ] `EXPLAIN ANALYZE`: `/decisions` 조회 index scan 확인
- [ ] 프론트 빌드·린트 에러 0
- [ ] Backend mypy/ruff 에러 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **R1**: SSE Bridge 에서 decision 누락 (네트워크 끊김 순간 발생 이벤트) | High | Medium | 기동 시 FarmOS 최신 `timestamp` 이후 Relay `/decisions?since=…` backfill. 재접속 후에도 동일 backfill 재실행. `id` UNIQUE 로 중복 INSERT 회피(UPSERT DO NOTHING). |
| **R2**: Relay 쪽 patch 적용 전 FarmOS 만 머지되면 Bridge 가 항상 404 | Medium | High | `AI_AGENT_BRIDGE_ENABLED=false` 기본값. Relay 패치 적용 완료 후 수동 활성화. Worker 는 기능 플래그 체크. |
| **R3**: 고빈도 decision(스톰) 시 Worker 가 싱글 코루틴 병목 | Medium | Low | batch flush(50 건 또는 2 초) + 요약 UPSERT 는 day/hour key 로 소수 행 충돌만 발생 → 성능 영향 제한적. |
| **R4**: 양쪽 DB 에 동일 `AIDecision.id` 가 저장되나 Relay 측 UUID 생성 규칙 변경 시 충돌 | Low | Low | Relay 의 `id` 를 FarmOS PK 로 그대로 사용, FarmOS 측 생성 로직 없음. 명시 주석. |
| **R5**: 30일 TTL cleanup 이 장시간 lock 유발 | Low | Low | 하루 1 회 batch DELETE + `VACUUM (ANALYZE)`, off-peak 시간. |
| **R6**: 프론트 기존 "전체 N건 보기" UX 회귀 | Medium | Medium | 기존 동작(roll-up N=20)은 요약 영역 상단에서 유지. "더보기"는 그 아래 전용 영역. A/B 없이 단일 UX. |
| **R7**: `tool_calls`·`action`·`sensor_snapshot` payload 크기 증가로 JSONB 인덱싱 필요 여부 | Low | Medium | v1 은 인덱싱 없이 `timestamp DESC` + `control_type` 단일 컬럼 인덱스만. 성능 이슈 발생 시 GIN 인덱스 추가. |
| **R8**: Relay 측 `/ai-agent/stream` SSE 구현이 현재 이벤트만 보내고 history replay 안 함 | High | High | Bridge 는 **SSE 실시간 + HTTP backfill** 두 채널 병행. SSE 단독 의존 금지. |

---

## 6. Impact Analysis

> **Purpose**: 본 feature 가 건드리는 리소스의 기존 소비자를 전부 나열해 회귀를 방지한다.

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `iot_agent_decisions` (Relay DB) | 신규 DB Table (Relay iot-postgres) | patch-spec 으로 추가. id/timestamp/control_type/priority/source/reason/action(JSONB)/tool_calls(JSONB)/sensor_snapshot(JSONB)/duration_ms/created_at |
| `ai_agent_decisions` (FarmOS DB) | 신규 DB Table (FarmOS farmos) | 동일 shape 미러 테이블 |
| `ai_agent_activity_daily` | 신규 DB Table | (day, control_type) PK, count / avg_duration_ms / by_source(JSONB) / by_priority(JSONB) |
| `ai_agent_activity_hourly` | 신규 DB Table | (hour, control_type) PK, 동일 집계 |
| `GET /ai-agent/decisions` (Relay) | API 확장 | 기존 `limit` only → `cursor` + 필터 파라미터 추가 |
| `GET /ai-agent/decisions/{id}` (Relay) | 신규 API | 단건 상세 |
| `GET /api/v1/ai-agent/activity/summary` (FarmOS) | 신규 API | 집계 |
| `GET /api/v1/ai-agent/decisions` (FarmOS) | 신규 API | 미러 목록 + 필터 |
| `GET /api/v1/ai-agent/decisions/{id}` (FarmOS) | 신규 API | 단건 상세 |
| `useAIAgent` 훅 | FE 훅 수정 | `API_BASE` 를 FarmOS BE 로 전환, `fetchMore`/`fetchDetail` 추가 |
| `AIAgentPanel` | FE 컴포넌트 수정 | 요약 카드 / 더보기 / row click → 모달 |
| `AIDecisionDetailModal` | FE 컴포넌트 신규 | 상세 모달 |
| `AIDecision` 타입 | TS type 확장 | 옵셔널 필드 추가 (`sensor_snapshot`, `duration_ms`, `id` 필수화) |
| `docs/backend-architecture.md` | Doc | Bridge Worker 섹션 추가 |
| `docs/database-schema.md` | Doc | 3 테이블 ERD/정의 추가 |
| `docs/iot-relay-server-postgres-patch.md` | Doc | §10 `iot_agent_decisions` 섹션 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `useAIAgent` | READ | `frontend/src/modules/iot/AIAgentPanel.tsx` | **Needs verification** — status/decisions shape 변동. 옵셔널 필드로 후방호환. |
| `onAIDecisionEvent` | SUBSCRIBE | `frontend/src/hooks/useSensorData.ts` | None — 이벤트 shape 상위호환 유지. 신규 필드는 무시 가능. |
| `AIDecision` type | READ | `frontend/src/types/index.ts`, `frontend/src/modules/iot/AIAgentPanel.tsx` | **Breaking if id required without migration** → `id` 는 Relay 가 이미 주고 있다고 가정. 서버에서 누락 시 FE 가 fallback (timestamp 기반 key). |
| Relay `GET /ai-agent/decisions` | READ | (현) FE `useAIAgent`, (후) FarmOS Bridge | **Contract Change** — `limit` only → `cursor` 추가. `limit` 생략 시 기존 동작 유지(호환). |
| FarmOS `backend/app/main.py` lifespan | LIFECYCLE | 기존 DB init | **Needs verification** — Bridge task 추가로 기동 지연 가능. SSE 연결 실패해도 앱 기동은 지속. |
| FarmOS Postgres (`farmos` DB) | WRITE | 기존 auth / journal / diagnosis / reviews 테이블 | None — 테이블명 `ai_agent_*` 로 격리, 외래키 없음. |

### 6.3 Verification

- [ ] `useAIAgent` 소비자 3 곳 (AIAgentPanel 본체 + CropProfileModal + `onAIDecisionEvent`) 회귀 테스트
- [ ] Relay `GET /ai-agent/decisions` 기존 쿼리(limit only) 가 계속 동작
- [ ] FarmOS 기존 테이블·조회에 영향 없음(전수 grep: `ai_agent_` 접두사 충돌 확인)
- [ ] Bridge Worker 실패가 메인 BE 기동을 막지 않음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, React + FastAPI + Postgres | Web apps with backend | ☑ |
| **Enterprise** | Strict layer separation, DI, microservices | High-traffic systems | ☐ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Framework (FE) | React / Next.js | **React (Vite)** | 기존 프로젝트 유지 |
| State Management | Context / Zustand / react-query | **로컬 훅(useAIAgent)** | 단일 패널, 전역 상태 불필요 |
| API Client | fetch | **fetch** | 기존 스타일 유지 |
| Pagination 방식 | offset / **keyset(cursor)** / relay-cursor | **keyset(cursor = created_at DESC)** | 30 일 range 고정 정렬 + index-only scan, page drift 방지 |
| Bridge 방식 | Pull polling / Push webhook / **SSE 구독** / WebSocket | **SSE + HTTP backfill 병행** | Relay 가 이미 SSE 보유, Relay 코드 추가 최소 |
| DB 테이블 분리 | 단일 Relay DB / **Relay + FarmOS 미러** / FarmOS only | **Relay + FarmOS 미러** | 서버 조작 금지 + AI 기능은 FarmOS 책임 |
| 요약 저장 | 실시간 집계 쿼리 / **사전 집계 테이블 UPSERT** | **사전 집계(daily + hourly)** | 30 일 집계 응답 p95 < 150 ms 보장 |
| action/tool_calls 저장 타입 | TEXT / **JSONB** / 정규화 테이블 | **JSONB** | shape 가변, 쿼리 빈도 낮음, 인덱스 GIN 보류 |
| TTL 정책 | 없음 / **30 일** / 90 일 | **30 일** | FarmOS 는 "요약 + 최근 원본" 역할 한정 |
| 테스트 | Vitest / **pytest + Playwright** | pytest + Playwright | 기존 프로젝트 표준 |

### 7.3 Clean Architecture Approach

```
Dynamic Level — Feature-based:

backend/app/
├── models/
│   ├── iot.py                     (선행: iot_postgres_migration)
│   └── ai_agent.py                ★신규 — 3 테이블 ORM
├── schemas/
│   └── ai_agent.py                ★신규 — Pydantic (Decision, Summary, Cursor)
├── services/
│   └── ai_agent_bridge.py         ★신규 — SSE Worker + backfill + 요약 UPSERT
├── api/
│   └── ai_agent.py                ★신규 — 3 엔드포인트
├── core/
│   ├── config.py                  수정 (IOT_RELAY_BASE_URL 등)
│   └── database.py                기존 init_db() 재사용
└── main.py                        lifespan 에 bridge task 등록

frontend/src/
├── hooks/
│   └── useAIAgent.ts              수정 — base URL, fetchMore, fetchDetail
├── modules/iot/
│   ├── AIAgentPanel.tsx           수정 — 요약 카드 + 더보기 + row click
│   ├── AIDecisionDetailModal.tsx  ★신규 — 상세 모달
│   └── AIActivitySummaryCards.tsx ★신규 — 오늘/7d/30d 탭
└── types/
    └── index.ts                   AIDecision 확장
```

### 7.4 Data Flow

```
┌──────────────────┐   HTTP POST /sensors   ┌───────────────────┐
│ ESP8266          │────────────────────────▶│ N100 Relay        │
└──────────────────┘                         │  iot-relay :9000  │
                                             │  ┌─────────────┐  │
                                             │  │ AI Engine   │  │
                                             │  └──────┬──────┘  │
                                             │         │         │
                                             │         ▼         │
                                             │  iot-postgres     │
                                             │  iot_agent_      │
                                             │  decisions(신규) │
                                             └────┬──────────────┘
                                                  │ SSE ai_decision
                                                  │ + HTTP backfill
                                                  ▼
                                           ┌──────────────────┐
                                           │ FarmOS BE        │
                                           │ Bridge Worker    │
                                           │  └─> ai_agent_   │
                                           │      decisions   │
                                           │      + daily/    │
                                           │      hourly      │
                                           │      UPSERT      │
                                           └────┬─────────────┘
                                                │ 3 API
                                                ▼
                                           ┌──────────────┐
                                           │ React FE     │
                                           │ - Summary    │
                                           │ - List(cursor│
                                           │ - Detail모달 │
                                           └──────────────┘
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` / project memory 에 서버 토폴로지·조작 금지 명시
- [x] `backend/app/core/database.py` async SQLAlchemy + `init_db()` 패턴 존재
- [x] `backend/app/api/*` FastAPI router 패턴 확립
- [x] `frontend/src/modules/iot/` 기존 IoT 모듈 구조 존재
- [x] `docs/iot-relay-server-postgres-patch.md` patch-spec 문서 형식 확립
- [ ] Bridge Worker(장기 실행 background task) 패턴은 이번에 신설

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Background task 기동** | 미존재 | `main.py` lifespan 에 `asyncio.create_task()` + 종료 시 `cancel + wait` | High |
| **SSE 파서** | 미존재 | `httpx.AsyncClient.stream("GET", url)` + `aiter_lines()` + `data:` 프리픽스 파싱 | High |
| **UPSERT** | 미존재 | `INSERT … ON CONFLICT (day, control_type) DO UPDATE SET …` | High |
| **JSONB 직렬화** | 미존재 | SQLAlchemy `JSONB` 컬럼 + Pydantic `Any` 매핑 | Medium |
| **Cursor pagination** | 미존재 | `created_at < :cursor` 으로 고정, 응답에 `next_cursor` 포함 | Medium |
| **Bridge 로그 포맷** | 기존 로깅 형식 따름 | `logger.info("bridge.event", extra={event, decision_id})` | Low |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `IOT_RELAY_BASE_URL` | Relay API 기본 URL (예: `https://iot.lilpa.moe`) | Backend | ☑ |
| `IOT_RELAY_API_KEY` | Relay X-API-Key 값 | Backend | ☑ |
| `AI_AGENT_BRIDGE_ENABLED` | Worker on/off 플래그 (default `false`) | Backend | ☑ |
| `AI_AGENT_MIRROR_TTL_DAYS` | 미러 TTL (default 30) | Backend | ☑ |
| `VITE_API_BASE` | 프론트가 FarmOS BE 로 호출하도록 변경 (기존 Relay 직접 호출 제거) | Frontend | ☑ (기존 키 재사용 확인) |

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 (Schema) | ☑ 반영 예정 | `docs/database-schema.md` 업데이트 | 수동 |
| Phase 4 (API) | ☑ 반영 예정 | `docs/02-design/features/agent-action-history.design.md` §4 | `/pdca design` |
| Phase 6 (UI Integration) | ☑ 반영 예정 | 동일 design §6 | `/pdca design` |

---

## 9. Next Steps

1. [ ] `docs/02-design/features/agent-action-history.design.md` 작성 (3 아키텍처 옵션 비교 + DDL/API 계약/컴포넌트 상세 + Session Guide Module Map)
2. [ ] iot-postgres-migration Design·Do 선행 완료 확인
3. [ ] Relay patch-spec 문서(`§10 iot_agent_decisions` 섹션) 초안 추가
4. [ ] FarmOS BE 모델/마이그레이션 → Bridge Worker → API 순차 구현 (swarm)
5. [ ] 프론트 상세 모달·더보기·요약 카드 구현
6. [ ] Gap 분석 (Match Rate ≥ 90%)
7. [ ] QA L1/L2/L3 시나리오 실행
8. [ ] Report 작성

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-20 | Initial draft (Team Mode /pdca team, Dynamic level, SSE Bridge + Mirror+Summary 선택) | clover0309 |
