# IoT 인메모리 → PostgreSQL 마이그레이션 Plan

| 항목 | 값 |
|------|-----|
| Feature | iot-postgres-migration |
| Author | FarmOS Team |
| Created | 2026-04-20 |
| Phase | Plan |

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| Problem | IoT 센서·관수·알림 데이터가 로컬 BE(`backend/app/core/store.py`)와 N100 Relay(`iot_relay_server/app/store.py`) 양쪽에서 인메모리(`deque` / `list`)에만 존재하여 서버 재시작 시 전부 소실된다. AI Agent가 과거 이력을 분석하는 기능이 실질적으로 동작하지 못한다. |
| Solution | 양쪽 저장소를 PostgreSQL 기반으로 전환한다. 로컬 BE는 기존 `farmos` DB에 `iot_` 접두사 3개 테이블을 추가하고, N100 Relay는 기존 다른 Postgres 와 격리된 **전용 컨테이너(`iot-postgres`)** 를 운영한다. |
| Function / UX Effect | 센서 히스토리가 재시작 후에도 유지되어 대시보드 그래프가 연속적으로 누적된다. 관수 이벤트·알림 타임라인이 영속화되어 운영 기록으로 남는다. |
| Core Value | AI Agent 의사결정의 신뢰성 확보 + 운영 지표 영속성 + 로컬/Relay 스토리지 전략 일관성. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | 인메모리 저장은 재시작마다 데이터가 사라져 AI Agent 추세 판단/회고가 불가능하고, 운영 타임라인이 휘발된다. |
| WHO | 김사과(Primary persona, 대시보드 조회), AI Agent(자동 제어 의사결정), 운영자(이력 감사). |
| RISK | (1) 로컬 BE와 N100 Relay가 각기 다른 PostgreSQL 인스턴스를 사용 → 이중 소스의 시점 차이. (2) asyncpg 의존성은 기존에 있으나 Relay 쪽은 psycopg나 asyncpg 신규 도입 필요. (3) `_prev_soil_moisture` 같은 모듈 상태는 DB 저장 대상이 아님(파생 값). |
| SUCCESS | (SC-1) 서버 재시작 후 `GET /sensors/history?limit=50` 에 이전 데이터가 남아 있다. (SC-2) `iot_sensor_readings` / `iot_irrigation_events` / `iot_sensor_alerts` 3개 테이블이 `farmos` DB에 생성된다. (SC-3) 기존 API 응답 JSON shape(camelCase)이 변하지 않아 프론트엔드 회귀가 없다. (SC-4) `/health` 응답의 `storage`가 `"postgres"`로 바뀐다. |
| SCOPE | IN: 로컬 BE `store.py`/models/routes, N100 Relay 코드 패치 스펙, 관련 docs 3건(`database-schema.md`, `backend-architecture.md`, `iot-relay-server-plan.md`). OUT: ESP8266 펌웨어, 프론트엔드 훅, AI Agent 규칙 로직, 이전 인메모리 데이터 이관. |

---

## 1. 배경

- 로컬 BE와 N100 Relay는 동일한 `/api/v1/sensors/*`, `/api/v1/irrigation/*` 계열 엔드포인트를 가지며 각자 인메모리 저장소를 운영한다.
- 프로젝트는 이미 PostgreSQL 18 + SQLAlchemy 2.0(async) + asyncpg를 사용해 사용자/저널/진단/리뷰 데이터를 영속 저장 중이다.
- N100 Relay 측에도 다른 Docker 컨테이너로 PostgreSQL이 구동 중이므로, Relay도 Docker Compose 네트워크 내부에서 DB 컨테이너에 접속할 수 있다.
- 본 레포에는 `iot_relay_server/` 디렉터리가 존재하지 않는다(N100에만 존재). → Relay 쪽은 **패치 스펙 문서**로 제공하고 사용자가 N100에 직접 적용한다.

## 2. 요구사항

### 2.1 기능 요구

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-1 | 센서 수신(POST) 시 DB 레코드 insert + 임계값 초과 시 알림/관수 이벤트 자동 insert | P0 |
| FR-2 | 최신 센서값(1건) 조회는 `timestamp DESC LIMIT 1` 쿼리로 제공 | P0 |
| FR-3 | 시계열 히스토리 조회는 `timestamp DESC LIMIT N` 후 오름차순으로 정렬 | P0 |
| FR-4 | 알림 목록 조회, `resolved` 필터 지원, `PATCH /resolve` 지원 | P0 |
| FR-5 | 수동 관수 트리거로 이벤트 insert, 이벤트 목록 최신순 조회 | P0 |
| FR-6 | `/health` 응답에 PostgreSQL 연결 상태 + 3개 테이블의 row count 포함 | P1 |
| FR-7 | 토양 습도 추정 시간 관성(`_prev_soil_moisture`)은 프로세스 내 상태로 유지(DB 비저장) | P1 |

### 2.2 비기능 요구

| ID | 내용 |
|----|------|
| NFR-1 | 기존 API 응답 JSON shape(camelCase 키)은 변경 없음 → 프론트엔드 무변경 |
| NFR-2 | 로컬 BE는 기존 `async_session` / `get_db()` depends를 재사용한다 |
| NFR-3 | N100 Relay는 sync psycopg 또는 asyncpg 중 Relay 코드베이스에 더 가벼운 쪽 선택 (본 문서에서는 **asyncpg**로 통일) |
| NFR-4 | 앱 기동 시 `CREATE TABLE IF NOT EXISTS` 로 멱등 생성 (기존 `init_db()` Flow에 편승) |
| NFR-5 | insert/query 실패해도 API는 5xx로 명시 에러 반환, 무음 실패 금지 |

## 3. 범위

### 3.1 포함 (In-scope)

1. 로컬 BE
   - `backend/app/models/iot.py` 신규 (3 테이블 ORM 모델)
   - `backend/app/core/store.py` → PostgreSQL 쿼리 기반으로 전면 재작성 (함수 시그니처에 `db: AsyncSession` 추가)
   - `backend/app/api/sensors.py`, `irrigation.py`, `health.py` 수정 (DB 세션 주입)
   - `backend/app/main.py` 모델 import 추가로 `Base.metadata` 등록
2. N100 Relay 패치 스펙
   - `docs/iot-relay-server-postgres-patch.md` 신규: Relay 측 `app/store.py` 치환본, `docker-compose.yml` 네트워크/환경변수 가이드, DDL SQL
3. 기존 IoT 관련 docs 업데이트
   - `docs/database-schema.md`: 인메모리 구간 제거, `iot_*` 3 테이블 추가
   - `docs/backend-architecture.md`: "데이터 저장 (IoT) 인메모리" → PostgreSQL로 변경, `store.py` 설명 갱신
   - `docs/iot-relay-server-plan.md`: §3 구조, §8 보안 노트를 PostgreSQL 버전으로 재명세

### 3.2 제외 (Out-of-scope)

- 프론트엔드 훅/페이지 수정 (API 응답 shape 유지하므로 불필요)
- ESP8266 펌웨어 (HTTP 계약 불변)
- AI Agent 규칙 로직 변경 (센서 조회 API 경유하므로 영향 없음)
- 기존 인메모리 데이터의 DB 이관 (사용자 요구: 깨끗하게 시작)

## 4. 수용 기준 (Acceptance Criteria)

| ID | 기준 | 검증 방법 |
|----|------|-----------|
| AC-1 | `start-all.bat` 재시작 후 `GET /api/v1/sensors/history?limit=50` 가 이전 세션 데이터를 포함 | 수동 재시작 + curl |
| AC-2 | `farmos` DB에 `iot_sensor_readings` / `iot_irrigation_events` / `iot_sensor_alerts` 3개 테이블 존재 | `\dt` 또는 `information_schema.tables` 쿼리 |
| AC-3 | 기존 `/api/v1/sensors/latest` 응답 키가 `soilMoisture`, `temperature`, `humidity`, `lightIntensity`, `timestamp`, `device_id` 그대로 | 응답 diff |
| AC-4 | `/api/v1/health` 응답의 `storage` 필드가 `"postgres"`이고 `readings_count` 가 DB 실제 count 와 일치 | curl + psql `SELECT COUNT(*)` |
| AC-5 | N100 Relay 패치 스펙을 적용하고 Docker Compose 재기동 후 ESP8266 POST → Relay DB에 row 추가됨 | docker logs + psql |
| AC-6 | 토양습도 임계치 이하 POST 시 `iot_sensor_alerts` + `iot_irrigation_events` 에 자동 row 추가 | POST 후 DB 조회 |

## 5. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| N100 Relay가 DB 컨테이너와 다른 Docker 네트워크에 있음 | Relay 시작 실패 | Docker Compose 로 같은 네트워크 배치 + `DATABASE_URL` 환경변수 주입 가이드 문서화 |
| asyncpg URL 스펙 차이 (`postgresql+asyncpg://` vs `postgresql://`) | 연결 실패 | 로컬/Relay 모두 `postgresql+asyncpg://` 통일, Relay asyncpg 의존성 추가 명시 |
| Alert/Irrigation 자동 insert 트랜잭션 실패 시 센서 reading만 저장됨 | 일관성 | 단일 commit 로 묶어 rollback 가능하게 처리 |
| 로컬과 Relay가 각기 다른 DB → 데이터 분산 | 운영 혼란 | 로컬 BE는 프론트 대시보드/AI Agent 전용, Relay는 ESP8266 수신 전용으로 역할 분리 유지 (현재와 동일) |

## 6. 참조 문서

- `docs/database-schema.md` — 기존 DB 설계
- `docs/backend-architecture.md` — 기존 BE 아키텍처
- `docs/iot-relay-server-plan.md` — 기존 Relay 계획 (인메모리 버전)
- `docs/iot-ai-agent-implementation.md` — AI Agent 구현 (센서 조회 API 의존)
- `.claude/projects/E--new-my-study-himedia-FinalProject-FarmOS/memory/project_server_topology.md` — 서버 토폴로지 (조작 금지 원칙)
