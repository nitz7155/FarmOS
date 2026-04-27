# automation/

Web_Starter NodeJS 자동화 — DB 검증 → Phase 1/2 분기 호출 → 재검증.

**의존성 없음.** 단일 `.mjs` 스크립트로 동작. `npm install` 불필요.

## 책임

1. `bootstrap/export_meta.py` 호출 → SQLAlchemy 모델 메타 + 시드 기대값 로드.
2. 시스템 `psql` 으로 `information_schema` 조회 → 테이블/컬럼/row 수 검증.
3. plan §2 분기표대로 `python bootstrap/create_tables.py` / `bootstrap/insert_data.py` 호출.
4. 재검증.
5. exit code 반환 (Web_Starter.exe 가 후속 backend/frontend 실행 결정).

NodeJS 는 backend/frontend 자체는 실행하지 않는다 — C# `ServerManager.StartAll()` 의 책임.

## 시스템 요구사항

| 도구 | 용도 | 확인 방법 |
|---|---|---|
| Node.js 22+ | `.mjs` ESM 실행 | `node --version` |
| `psql` | PostgreSQL 쿼리 | `psql --version` (PATH 에 있어야 함) |
| `python` | bootstrap 스크립트 호출 | `python --version` |

## 실행

```bash
node automation/run.mjs
```

또는 cwd 무관하게:

```bash
node E:/new_my_study/FarmOS-Real/FarmOS/automation/run.mjs
```

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `FARMOS_PROJECT_ROOT` | (자동 추론) | repo 루트. 미지정 시 `automation/..` |
| `PG_HOST` / `PGHOST` | `localhost` | PostgreSQL 호스트 |
| `PG_PORT` / `PGPORT` | `5432` | 포트 |
| `PG_DATABASE` / `PGDATABASE` | `farmos` | DB 이름 |
| `PG_USER` / `PGUSER` | `postgres` | 사용자 |
| `PG_PASSWORD` / `PGPASSWORD` | `root` | 비밀번호 |

C# `AppSettings.Instance` 가 자식 프로세스에 주입한다.

## Exit Code 규약

| Code | 의미 | C# 처리 |
|---|---|---|
| `0` | 검증 통과 | `StartAll()` 진행 |
| `10` | 컬럼 타입 drift 감지 (자동 ALTER 금지) | 메시지박스 표시, `StartAll()` 중단 |
| `20` | 재검증 실패 (시드 후에도 결함) | 로그 표시, `StartAll()` 중단 |
| `30` | 환경 오류 (psql/python/메타 로드) | 메시지박스 표시, `StartAll()` 중단 |
| `40` | Phase 호출 실패 (Python 시드 스크립트 비정상 종료) | 로그 표시, `StartAll()` 중단 |
| `1`  | 예상치 못한 예외 | 로그 표시, `StartAll()` 중단 |

## 분기 (plan §2)

| 검증 결과 | 호출 |
|---|---|
| 테이블 없음 또는 컬럼 누락 | Phase 1 → Phase 2 |
| 컬럼·테이블 OK, 데이터만 부족 | Phase 2 |
| 모두 정상 | 둘 다 스킵 |
| 컬럼 타입 drift 만 있음 | 중단(exit 10) |
