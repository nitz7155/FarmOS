# IoT 인메모리 → PostgreSQL 마이그레이션 Design

| 항목 | 값 |
|------|-----|
| Feature | iot-postgres-migration |
| Phase | Design |
| Created | 2026-04-20 |

## Context Anchor (from Plan)

| Key | Value |
|-----|-------|
| WHY | 인메모리 저장은 재시작 시 소실 → AI Agent 회고/추세 판단 불가, 운영 타임라인 휘발 |
| WHO | 김사과(대시보드), AI Agent(자동 제어), 운영자(이력 감사) |
| RISK | 로컬/Relay 별도 DB 운영, asyncpg 의존성 추가, 파생 상태(`_prev_soil_moisture`) 비저장 |
| SUCCESS | 재시작 후 이력 유지 / iot_* 3 테이블 / 응답 shape 무변경 / `/health.storage=postgres` |
| SCOPE | IN: BE 코드+3 docs+Relay 패치 스펙. OUT: 프론트/ESP/데이터 이관 |

---

## 1. 아키텍처 개요

```
 ┌──────────────┐ POST /api/v1/sensors  ┌──────────────────────┐
 │  ESP8266     │ ────────────────────► │  N100 Relay Server   │
 │ DHT11+CdS    │                       │  (FastAPI Docker)    │
 └──────────────┘                       │                      │
                                        │  app/store_pg.py     │
                                        │  (asyncpg session)   │
                                        │         │            │
                                        │         ▼            │
                                        │  ┌────────────────┐  │
                                        │  │ PostgreSQL     │  │
                                        │  │ (Docker 동일   │  │
                                        │  │  네트워크)      │  │
                                        │  └────────────────┘  │
                                        └──────────────────────┘

 ┌─────────────────────┐  GET /api/v1/sensors/*   ┌──────────────────────┐
 │ 프론트엔드 / AI Agent│ ────────────────────────►│  로컬 BE (FarmOS)     │
 │ (localhost:5173 등)  │                          │  FastAPI Python 3.12 │
 └─────────────────────┘                          │                      │
                                                  │  app/core/store.py   │
                                                  │  (SQLAlchemy async)  │
                                                  │         │            │
                                                  │         ▼            │
                                                  │  PostgreSQL farmos   │
                                                  │  (localhost:5432)    │
                                                  └──────────────────────┘
```

- 로컬 BE와 N100 Relay는 **각기 다른 PostgreSQL 인스턴스**를 사용한다. 현재와 동일한 역할 분리(로컬=프론트/AI Agent, Relay=ESP 수신)를 유지한다.
- 스키마는 양쪽 동일(`iot_sensor_readings`, `iot_irrigation_events`, `iot_sensor_alerts`).

## 2. 데이터 모델

### 2.1 `iot_sensor_readings`

| Column | Type | Nullable | Index | 비고 |
|--------|------|:--------:|:-----:|------|
| id | UUID | NO | PK | `uuid4()` default |
| device_id | VARCHAR(64) | NO | ✓ | ESP8266 식별자 |
| timestamp | TIMESTAMPTZ | NO | ✓ (DESC) | ESP 전송 시각, 조회 정렬 키 |
| soil_moisture | FLOAT | NO | - | 추정치 포함 |
| temperature | FLOAT | NO | - |  |
| humidity | FLOAT | NO | - |  |
| light_intensity | INTEGER | NO | - |  |
| created_at | TIMESTAMPTZ | NO | - | `now()` default |

인덱스: `(timestamp DESC)` — 최신 N건 조회가 압도적으로 많음.

### 2.2 `iot_irrigation_events`

| Column | Type | Nullable | 비고 |
|--------|------|:--------:|------|
| id | UUID | NO | PK |
| triggered_at | TIMESTAMPTZ | NO | 인덱스 (DESC) |
| reason | VARCHAR(255) | NO | 사유 텍스트 |
| valve_action | VARCHAR(10) | NO | "열림" / "닫힘" |
| duration | INTEGER | NO | 초 단위 |
| auto_triggered | BOOLEAN | NO | 자동 여부 |
| created_at | TIMESTAMPTZ | NO |  |

### 2.3 `iot_sensor_alerts`

| Column | Type | Nullable | 비고 |
|--------|------|:--------:|------|
| id | UUID | NO | PK |
| type | VARCHAR(32) | NO | "moisture" / "humidity" 등 |
| severity | VARCHAR(16) | NO | "경고" / "주의" |
| message | VARCHAR(255) | NO |  |
| timestamp | TIMESTAMPTZ | NO | 인덱스 (DESC) |
| resolved | BOOLEAN | NO | default FALSE |
| resolved_at | TIMESTAMPTZ | YES |  |
| created_at | TIMESTAMPTZ | NO |  |

## 3. API 계약 (응답 shape 보존)

```json
// GET /api/v1/sensors/latest
{
  "device_id": "esp8266-farm01",
  "timestamp": "2026-04-20T12:34:56+00:00",
  "soilMoisture": 54.3,
  "temperature": 22.1,
  "humidity": 60.4,
  "lightIntensity": 38000
}

// GET /api/v1/irrigation/events → list of
{
  "id": "uuid",
  "triggeredAt": "2026-04-20T12:34:56+00:00",
  "reason": "수동 제어",
  "valveAction": "열림",
  "duration": 30,
  "autoTriggered": false
}
```

DB 컬럼(snake_case) → 응답 키(camelCase) 변환은 저장소 모듈의 `_row_to_*` helper에서 수행.

## 4. 모듈 구성 (Local BE)

| 경로 | 변경 | 역할 |
|------|------|------|
| `backend/app/models/iot.py` | **신규** | 3개 SQLAlchemy 모델 + 인덱스 정의 |
| `backend/app/core/store.py` | **전면 수정** | 함수 시그니처에 `db: AsyncSession` 추가, PostgreSQL 쿼리로 재작성. `_prev_soil_moisture` 모듈 상태는 유지 |
| `backend/app/api/sensors.py` | 수정 | 모든 라우트에 `db: AsyncSession = Depends(get_db)` 추가, await 적용 |
| `backend/app/api/irrigation.py` | 수정 | 동일 |
| `backend/app/api/health.py` | 수정 | `SELECT COUNT(*)` 로 카운트, `storage` 키를 `"postgres"` 로 변경 |
| `backend/app/main.py` | 수정 | `from app.models.iot import ...` 추가로 metadata 등록 |

## 5. N100 Relay 패치 (문서로 제공)

Relay 코드는 본 레포에 없으므로 `docs/iot-relay-server-postgres-patch.md` 에 다음을 명세:

1. DDL SQL (psql로 1회 실행)
2. 새 `app/store_pg.py` 전체 코드 (asyncpg + asyncpg.Pool 기반, FastAPI lifespan 에서 pool 생성/종료)
3. `app/main.py` diff — import 변경, `app.state.db_pool` 주입
4. `app/api/*` 라우트의 DI 수정
5. `docker-compose.yml` — **전용 `iot-postgres` 서비스** 신규 + `iot-relay` 서비스, 전용 `iot_net` 네트워크, `iot_pgdata` 볼륨, `depends_on.condition: service_healthy`
6. 기동 순서: `docker compose up -d --build` → iot-postgres initdb 훅이 `iot_init.sql` 자동 적용 → Relay 가 healthcheck 대기 후 기동

## 6. 세부 로직

### 6.1 `add_reading` 트랜잭션

```
BEGIN
  INSERT iot_sensor_readings (...);
  IF soil_moisture < threshold THEN
    INSERT iot_sensor_alerts (moisture);
    INSERT iot_irrigation_events (auto);
  END IF;
  IF humidity > 90 THEN
    INSERT iot_sensor_alerts (humidity);
  END IF;
COMMIT;
```

- 단일 `async with db.begin()` 블록에서 처리 → 실패 시 전체 rollback.
- 반환값: `list[dict]` (새로 생성된 alert 목록, 기존 계약 유지).

### 6.2 토양습도 추정

- 기존 `_estimate_soil_moisture` 함수는 그대로 유지.
- `_prev_soil_moisture` 는 로컬 BE 모듈 레벨에서 1개 프로세스 스코프로 둠 (DB 저장 불필요 — 부드러운 스무딩용).
- Relay 측도 동일하게 모듈 상태로 유지.

### 6.3 `/health` 조회

```python
row_count = await db.scalar(select(func.count()).select_from(IotSensorReading))
```

- 3개 테이블의 count + DB 연결 상태(`SELECT 1`) 확인.

## 7. Alternative 고려 내역

| 옵션 | 내용 | 선택 여부 |
|------|------|:--------:|
| A. 단일 DB 일원화 | Relay가 로컬 PostgreSQL에 원격 접속 | ✗ (네트워크/방화벽 리스크) |
| B. 로컬/Relay 각자 DB | 역할 분리 유지, 스키마만 공유 | **✓ 선택** |
| C. 이벤트 스트림(Kafka 등) | 과도한 인프라 | ✗ |

## 8. Test Plan

| 레벨 | 항목 | 방법 |
|------|------|------|
| L1 API | POST /sensors, GET latest/history/alerts, PATCH resolve, POST irrigation/trigger | curl 스크립트 |
| L1 API | /health storage=postgres 확인 | curl |
| L2 회귀 | 서버 재시작 후 history 유지 | 재기동 후 curl |
| L2 회귀 | 프론트엔드 대시보드 그래프 렌더 | 수동 브라우저 |
| L3 E2E | ESP8266 → Relay → DB → 프론트 조회 (운영환경 시나리오) | ESP 펌웨어 동작 중 관찰 |

## 9. 구현 순서

1. DDL 모델 정의 (`models/iot.py`)
2. 저장소 모듈 재작성 (`core/store.py`)
3. API 라우트 DI 수정 (sensors/irrigation/health)
4. `main.py` import 추가
5. 로컬 재기동 + curl 스모크
6. 기존 docs 3건 업데이트
7. N100 Relay 패치 스펙 문서 작성
