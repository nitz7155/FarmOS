# Bootstrap 리팩터 + NodeJS 자동화 + C# 통합 — 완료 보고

> 작성일: 2026-04-27
> 짝 문서: `docs/bootstrap-refactor-plan.md` (시작점 명세)
> 작업 범위: `bootstrap/`, `automation/` (신규), `Web_Starter.exe` (C# 런처)

이 문서는 plan 문서 §8 의 모든 단계를 실행한 결과와, 그 과정에서 발견·결정한 추가 사항을 기록한다. plan 의 "예정" 표현은 모두 "완료" 또는 "유보" 로 결론지어졌다.

---

## 1. 작업 범위 한눈에 보기

| Phase | 내용 | 결과 |
|---|---|---|
| **1. bootstrap 리팩터** | plan §1~5 실행 (삭제·슬림화·5개 시드 리팩터·진입점 작성) | ✅ 완료 |
| **2. 동작 검증 패치** | Phase 1/2 실행 중 발견한 모델/SQL 이슈 수정 | ✅ 완료 |
| **3. NodeJS 자동화** | plan §6 — `automation/run.mjs` + `bootstrap/export_meta.py` | ✅ 완료 |
| **4. C# 통합** | `Web_Starter.exe` 서버시작 버튼 ↔ 자동화 연동 | ✅ 완료 |
| **5. 한글 깨짐 대응** | Windows 한국 로케일 stderr 인코딩 보정 | ✅ 완료 |
| **6. 회귀 테스트** | 데이터 부족 / 테이블 누락 / DB 미존재 3 시나리오 | ✅ 통과 |
| **7. 잔여 정리** | `bootstrap.py`, `bootstrap/farmos.py`, `bootstrap/shoppingmall.py` 처분 | ⏳ 유보 (별도 결정) |

---

## 2. Phase 1 — bootstrap 리팩터 결과

### 2.1 삭제 (plan §3.2)

| 파일 | 사유 |
|---|---|
| `bootstrap/_bootstrap_common.py` | ORM 0 줄, 100% psql/subprocess 오케스트레이션. NodeJS 가 대체 |
| `bootstrap/reset_db.py` | `DROP SCHEMA public CASCADE` 만. 의도적으로 폐기 |
| `bootstrap/__pycache__/` | 캐시 정리 |

### 2.2 슬림화 — `bootstrap/pesticide.py` (plan §3.4)

- 1215 줄 → **215 줄** 로 축소
- 보존: `Base(DeclarativeBase)` + 5 모델 (`Product`, `Crop`, `Target`, `ProductApplication`, `RagDocument`)
- 신규 함수: `create_pesticide_tables(engine)` — `Base.metadata.create_all(engine)` 한 줄
- 삭제: argparse, ETL 헬퍼, `Stats`/`UpsertCaches`, `populate_database`, `rebuild_tables`, `main()` 등 ~1000 줄

### 2.3 5 개 시드 파일 리팩터 (plan §3.3)

| 파일 | 노출 함수 | 핵심 변경 |
|---|---|---|
| `farmos_seed.py` | `seed_farmos_users()` | argparse/mode 분기/drop/truncate/NCPMS subprocess/pesticide subprocess 제거 |
| `ncpms_seed.py` | `seed_ncpms()` (no-arg) | `_bootstrap_common` 의존 제거 |
| `seed_ai_agent.py` | `seed_ai_agent(count=30)` | `sys.argv` 처리 제거 |
| `shoppingmall_seed.py` | `seed_shoppingmall()` | argparse/truncate/run_*_pipeline/_to_sync_db_url 제거 + 멱등 가드(`shop_categories` count) 추가 |
| `shoppingmall_review_seed.py` | `seed_shoppingmall_reviews()` | **`DELETE FROM shop_reviews` 제거 → `ON CONFLICT (id) DO NOTHING`** |

### 2.4 신규 진입점

| 파일 | 역할 |
|---|---|
| `bootstrap/create_tables.py` | Phase 1 — `init_db()` + `pesticide Base.metadata.create_all` |
| `bootstrap/insert_data.py` | Phase 2 — 5 개 `seed_*()` 함수 순차 호출 |

#### 설계 결정 — 듀얼 venv subprocess 분기

`backend/app` 와 `shopping_mall/backend/app` 가 같은 패키지명 `app` 을 쓰고 의존(asyncpg vs psycopg2) 도 분리되어 있어 단일 Python 프로세스에서 동시 import 불가. 따라서 두 진입점은 **각 backend 의 `.venv/Scripts/python.exe` 로 subprocess 분기**한다 (plan §3.4 의 "한 프로세스에서 직접 import" 예시는 현실적으로 불가능, 우회).

NodeJS 가 단일 진입점만 호출한다는 plan 계약(`python bootstrap/create_tables.py`) 은 그대로 유지.

### 2.5 파괴적 로직 제거 — 정적 검증 결과

`grep -E "DROP|TRUNCATE|DELETE FROM|drop_all\(|ALTER TABLE"` → 모든 매치가 docstring(주석/설명) 안. 실제 실행 코드에 0 건.
`ON CONFLICT` 패턴 → 4 개 시드 파일에 12 곳 분포.
`py_compile` → 8 개 파일 모두 syntax OK.

---

## 3. Phase 2 — 동작 검증 중 발견한 이슈와 패치

Phase 1/2 실행 중 두 가지 추가 결함이 표면화되어 즉시 수정.

### 3.1 `ai_agent_activity_daily.duration_count` NOT NULL 누락

- **현상**: `seed_ai_agent` 실행 시 `NotNullViolationError: "duration_count"`
- **원인**: 모델 (`backend/app/models/ai_agent.py`) 에 `duration_count INTEGER NOT NULL DEFAULT 0`, `duration_sum BIGINT NOT NULL DEFAULT 0` 가 추가되어 있는데 `seed_ai_agent.py` 의 raw SQL INSERT 가 두 컬럼을 채우지 않음
- **수정** (`bootstrap/seed_ai_agent.py`):
  - INSERT 컬럼 + VALUES 에 `duration_count`, `duration_sum` 추가
  - `avg_duration_ms` 계산식을 모델 docstring 의도에 맞춰 `duration_sum / duration_count` 기반으로 변경 (null-duration 행을 분모/분자에서 제외 → 편향 없음)

### 3.2 asyncpg `AmbiguousParameterError`

- **현상**: 같은 파라미터 `:dur` 가 INSERT VALUES, `IS NULL`, `COALESCE` 세 컨텍스트에서 동시에 사용되어 prepared statement 타입 추론 실패
- **수정**: Python 측에서 `dur_inc` (0/1), `dur_add` (int), `avg_dur` (int|None) 로 미리 분기 후 SQL 에는 정수만 전달. `IS NULL`/`COALESCE` SQL 분기 자체 제거 → SQL 단순화 + 타입 모호성 제거

---

## 4. Phase 3 — NodeJS 자동화 (`automation/`)

### 4.1 결정 — npm install 없는 단일 `.mjs`

초기에 TypeScript + `pg` 라이브러리 + `npm install` 구조로 시작했으나, 사용자 요청에 따라 **의존성 0** 으로 단순화. 시스템에 이미 있는 `psql` CLI 로 `pg` 라이브러리를 대체.

### 4.2 구성

```text
automation/
├── README.md          # 환경변수, exit code 규약, 분기표
├── run.mjs            # 단일 진입점 (의존성 0)
└── .gitignore
```

### 4.3 실행 흐름 (plan §1)

```text
[1] preflightCheck()       — postgres DB 접속으로 인증/연결/대상 DB 존재 확인
[2] loadMeta()             — bootstrap/export_meta.py 호출, JSON 받기
[3] verifyDatabase()       — psql 로 information_schema 조회 (테이블/컬럼/row 수)
[4] 분기 (plan §2)
       missing tables → Phase 1 + Phase 2 순차
       row deficit    → Phase 2 만
       column drift   → exit 10 (수동 마이그레이션 요청)
       정상           → 둘 다 스킵
[5] verifyDatabase() 재검증
[6] exit code 반환 (Web_Starter.exe 가 backend/frontend spawn 결정)
```

### 4.4 메타 추출 — `bootstrap/export_meta.py`

두 backend venv 로 subprocess 분기, 각자 SQLAlchemy 모델 메타를 JSON 으로 export:

```json
{
  "farmos": {
    "tables": { "<name>": { "columns": [...], "primary_key": [...] } },
    "expected_row_counts": {...},
    "post_pesticide_min_row_counts": {...},
    "ai_agent_default_count": 30
  },
  "shoppingmall": {
    "tables": {...},
    "expected_row_counts": {...},
    "ready_row_counts": {...},
    "review_target_count": 1000
  }
}
```

플랜 §6 의 "정적 파싱 vs Python export" 옵션 중 **Python export 채택** — 검증은 1 회만 실행되므로 spawn 비용은 무시 가능, 단일 진실 소스(Python) 유지.

### 4.5 Exit Code 규약

| Code | 의미 | C# 처리 |
|---|---|---|
| `0` | 검증 통과 | `StartAll()` 진행 |
| `10` | 컬럼 drift (자동 ALTER 금지) | 메시지박스 + 차단 |
| `20` | 재검증 실패 | 메시지박스 + 차단 |
| `30` | 환경 오류 (psql/python/메타/사전체크) | 메시지박스 + 차단 |
| `1`  | 자동화 예외 | 메시지박스 + 차단 |
| `-1` | `automation/run.mjs` 미존재 | C# 측 보호 |
| `-2` | 5 분 타임아웃 | C# 측 보호 |
| `-3` | C# 측 예외 (node 실행 실패) | C# 측 보호 |

### 4.6 검증 정책 — 컬럼 drift 처리

plan §4 "자동 ALTER 금지" 와 §6.5 "drift 시 중단" 정책을 다음과 같이 운용:

- **column missing / type_mismatch 모두** "drift" 로 묶어 처리
- drift 만 단독 → exit 10 (수동 개입)
- drift + 다른 결함 동반 → 경고만 표시, Phase 호출은 진행 (Phase 가 회복할 수 있는 부분은 회복)
- 재검증에 drift 가 남아있으면 **경고만** 하고 EXIT_OK (시드로는 못 고치므로)

### 4.7 자동화 제외 영역

`post_pesticide_min_row_counts` (rag_pesticide_*) 는 검증에서 제외 — plan §3.4 에 따라 **JSON raw 가 git 미포함**이라 사용자 수동 적재 영역. 자동화에 포함하면 영구 row deficit 으로 false fail.

---

## 5. Phase 4 — C# 통합 (`Web_Starter`)

### 5.1 변경 파일

| 파일 | 변경 |
|---|---|
| `AutomationRunner.cs` | **신규** — `node automation/run.mjs` spawn, exit code → 한글 메시지 매핑, stdout/stderr UTF-8 캡처, 5 분 타임아웃 |
| `Form1.cs` | 서버시작 버튼 핸들러에 자동화 호출 단계 추가, 실패 시 `StartAll()` **차단** |
| `Web_Starter.csproj` | `<Compile Include="AutomationRunner.cs" />` 등록 |

### 5.2 새 흐름

```text
[서버시작 클릭]
  ↓
1. ProjectRoot 확인 (실패 → 메시지박스 + 종료)
  ↓
2. textBox = "DB 검증 중..."
  ↓
3. AutomationRunner.Run(projectRoot)         ← NEW
   - AppSettings → PG_HOST/PG_PORT/.../PG_PASSWORD 환경변수 주입
   - node automation/run.mjs spawn (5 분 타임아웃)
   - stdout/stderr UTF-8 캡처
  ↓
4. result.Success == false (exit != 0 or 타임아웃)
   → 메시지박스 (요약 + 출력 마지막 4000 자) + 서버 시작 차단
  ↓
5. result.Success == true
   → ServerManager.StartAll() (기존 동작, 4 개 서비스 spawn)
```

### 5.3 폐기 (사용 중지)

`DatabaseChecker.cs` — 옛 `farmos_seed.py --mode ensure` CLI 인터페이스 호출. 이미 broken 상태(slim 화된 시드는 argparse 없음). 호출처 0. 정리 권장 (Npgsql PackageReference 동반 제거 가능).

---

## 6. Phase 5 — 한글 깨짐 대응

### 6.1 문제

Windows 한국 로케일 환경에서 PostgreSQL **서버** 가 한글로 보내는 FATAL 메시지가 cp949 로 인코딩되어 stderr 에 떨어짐 → node `encoding: "utf-8"` 디코딩 실패 → C# 메시지박스에 `g������` 식 깨짐.

`LC_MESSAGES=C` 는 psql 클라이언트 메시지만 영어로 강제할 뿐 서버 측 메시지엔 무력.

### 6.2 3 단계 대응 (`automation/run.mjs`)

1. **`PGOPTIONS=-c lc_messages=C`** — 서버 측 세션 lc_messages 도 영어 시도
2. **`safeDecodeStderr(buffer)`** — utf-8 fatal 디코드 시도, 실패 시 ASCII printable + 줄바꿈만 추출 (한글 깨진 바이트 → 공백)
3. **`preflightCheck()`** — `postgres` 시스템 DB 로 접속해 인증/연결/대상 DB 존재 여부를 우리가 직접 검증, **명확한 한글 메시지** throw

### 6.3 결과 — 시나리오별 사용자 메시지

| 잘못된 입력 | 메시지 |
|---|---|
| 비밀번호 오류 | "PostgreSQL 비밀번호가 잘못됐습니다 (user=...). 설정의 DbPassword 값을 확인하세요." |
| 잘못된 DB 이름 | "데이터베이스 \"...\" 가 존재하지 않습니다 (host=...:...)..." |
| PostgreSQL 미실행 | "PostgreSQL 서버(host:port) 에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요." |
| 잘못된 user (role) | "PostgreSQL 사용자(role) \"...\" 가 존재하지 않습니다." |
| pg_hba 거부 | "PostgreSQL pg_hba.conf 가 ... 에서의 접속을 허용하지 않습니다." |

---

## 7. 추가 발견 — 모델 동기화 (`backend/app/models/pesticide.py`)

### 7.1 문제

- `bootstrap/pesticide.py` (RagDocument 33 컬럼) 와 `backend/app/models/pesticide.py` (PesticideProduct 12 컬럼) 가 **같은 테이블명** (`rag_pesticide_documents`) 을 가진 채 **다른 컬럼 정의**
- `backend/app/models/__init__.py` 가 `PesticideProduct` 를 자동 import → backend 코드에서 `from app.models import *` 트리거 시 같은 `Base.metadata` 에 등록
- `init_db()` 실행 시점에 backend 정의 (12 컬럼) 로 작은 테이블이 먼저 생성됨 → 그 다음 `PesticideBase.metadata.create_all()` 은 IF NOT EXISTS 라 스킵 → 결과 DB 가 12 컬럼 옛 스키마

### 7.2 자동화 첫 출력 — `column issues=39`

`rag_pesticide_documents` 차이 21 + `rag_pesticide_product_applications` 차이 18 = 39. 우연히 팀원이 "한 테이블 컬럼이 39개" 라고 한 숫자와 일치하여 혼동 유발.

### 7.3 해결 (팀원 작업으로 pull 받음)

`backend/app/models/pesticide.py` 를 5 개 모델 풀 컬럼 정의로 동기화. 두 파일이 정확히 같은 87 컬럼 (24+5+6+19+33) 을 가지게 됨. `__init__.py` 도 5 개 모델 모두 export.

이후 사용자 환경에서 `DROP TABLE rag_pesticide_documents, rag_pesticide_product_applications CASCADE;` 후 자동화 재실행 → 풀 스키마로 재생성 → drift 0 확인.

---

## 8. 회귀 테스트 결과

| 시나리오 | 명령 | 분기 | exit | 결과 |
|---|---|---|---|---|
| **A. 데이터 부족** | `DELETE FROM shop_reviews WHERE id=1;` | Phase 2 만 호출 | 0 | ✅ 통과 |
| **B. 테이블 전부 없음** | `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` | Phase 1+2 순차 | 0 | ✅ 통과 |
| **C. DB 자체 없음** | `DROP DATABASE farmos;` | preflightCheck 차단 | 30 | ✅ 통과 (서버 시작 차단 확인) |

---

## 9. 운영 가이드

### 9.1 환경변수 (`automation/run.mjs`)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `FARMOS_PROJECT_ROOT` | (자동 추론) | repo 루트 |
| `PG_HOST` / `PGHOST` | `localhost` | PostgreSQL 호스트 |
| `PG_PORT` / `PGPORT` | `5432` | 포트 |
| `PG_DATABASE` / `PGDATABASE` | `farmos` | DB 이름 |
| `PG_USER` / `PGUSER` | `postgres` | 사용자 |
| `PG_PASSWORD` / `PGPASSWORD` | `root` | 비밀번호 |

C# `AppSettings.Instance` 가 자식 프로세스에 자동 주입.

### 9.2 시스템 요구사항

- Node.js 18+ (PATH)
- `psql` (PostgreSQL bin, PATH)
- `python` (PATH) + `backend/.venv`, `shopping_mall/backend/.venv`

### 9.3 단독 실행 (디버깅)

```bash
node automation/run.mjs                                    # 정상 실행
PG_PASSWORD=wrong node automation/run.mjs                  # 비밀번호 오류 시뮬
PG_DATABASE=invalid node automation/run.mjs                # DB 미존재 시뮬
```

### 9.4 .exe 배포

Visual Studio `Release` 빌드 → `Web_Starter.exe` + `Web_Starter.exe.config` 두 파일을 FarmOS 루트로 복사. Costura.Fody 가 의존 DLL 을 임베드하므로 단일 .exe 로 동작.

---

## 10. 유보된 작업 (plan Step 7)

`_bootstrap_common.py` 삭제로 import 가 깨진 상태로 남은 파일들:

| 파일 | 상태 | 처리 시점 |
|---|---|---|
| 루트 `bootstrap.py` | broken (예상됨) | NodeJS 도입 + `start-all.bat` 폐기 시점 |
| `bootstrap/farmos.py` | broken (서비스 실행 래퍼, NodeJS 가 대체) | 동상 |
| `bootstrap/shoppingmall.py` | broken (서비스 실행 래퍼) | 동상 |
| `bootstrap/Old_BootStrapBackup/` | 새 fork 환경엔 미존재 | 영구 유보 (현재 자동화 영향 없음) |
| `Web_Starter/DatabaseChecker.cs` | 호출 0, obsolete | C# 측 정리 시점 (Npgsql 의존도 동반 제거 가능) |
| `Web_Starter/Npgsql` PackageReference | DatabaseChecker 동행 정리 | 동상 |

세 시드 실행 래퍼(`bootstrap.py`/`farmos.py`/`shoppingmall.py`) 는 새 흐름에서 호출되지 않으므로 운영 영향 0. 향후 한 PR 로 함께 정리하는 것이 자연스럽다.

---

## 11. 핵심 의사결정 로그

| 결정 | 이유 |
|---|---|
| 듀얼 venv subprocess 분기 | 두 backend 의 `app` 패키지명 충돌 + 의존(asyncpg/psycopg2) 분리 |
| npm install 없는 단일 `.mjs` | 사용자 요구. 시스템 `psql` 로 `pg` 라이브러리 대체 |
| 메타 추출 = Python export → JSON | 정적 파싱보다 안정. 검증은 1 회 spawn 이라 비용 무시 |
| pesticide row 검증 자동화 제외 | plan §3.4 — JSON raw 가 git 미포함, 사용자 수동 적재 |
| column drift = 시드 호출 결정 비반영 | `Base.metadata.create_all` 이 IF NOT EXISTS 라 회복 불가, 별도 운영 영역 |
| 사전 체크 (preflightCheck) 도입 | psql 서버 측 한글 메시지가 인증 단계에서 깨지는 문제를 우회 |
| backend/frontend 실행은 C# 책임 | plan §1 [4]. NodeJS 는 검증/시드만, ServerManager 변경 없음 |

---

## 12. 변경 파일 목록 (요약)

### 새로 생성
- `automation/run.mjs`
- `automation/README.md`
- `automation/.gitignore`
- `bootstrap/export_meta.py`
- `bootstrap/create_tables.py`
- `bootstrap/insert_data.py`
- `Side_Project/C#/Web_Starter/Web_Starter/AutomationRunner.cs`

### 수정
- `bootstrap/pesticide.py` (1215 → 215 줄)
- `bootstrap/farmos_seed.py`
- `bootstrap/ncpms_seed.py`
- `bootstrap/seed_ai_agent.py`
- `bootstrap/shoppingmall_seed.py`
- `bootstrap/shoppingmall_review_seed.py`
- `backend/app/models/pesticide.py` (팀원 작업)
- `backend/app/models/__init__.py` (팀원 작업)
- `Side_Project/C#/Web_Starter/Web_Starter/Form1.cs`
- `Side_Project/C#/Web_Starter/Web_Starter/Web_Starter.csproj`

### 삭제
- `bootstrap/_bootstrap_common.py`
- `bootstrap/reset_db.py`
- `bootstrap/__pycache__/`
