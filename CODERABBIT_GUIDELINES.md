# FarmOS CodeRabbit Code Guidelines

## Python 코드 스타일

### 명명 규칙
- 함수/변수: snake_case
- 클래스: PascalCase
- 상수: UPPER_SNAKE_CASE
- Private: _leading_underscore

### 라인 길이
- 최대 100자 권장 (pyproject.toml 참고)

### 타입 힌팅
- 함수 서명에 타입 힌팅 권장
- SQLAlchemy Mapped[] 사용 (models)
- Pydantic BaseModel 스키마 활용

### 비동기 코드
- async def / await 일관성 확인
- FastAPI 핸들러는 async 권장

### 데이터베이스 패턴
- ✓ SQLAlchemy 2.0+ 패턴 (Mapped[])
- ✓ db: Session 의존성 주입
- ✓ ORM 쿼리 사용 (쿼리 빌더)
- ✗ 원본 SQL 쿼리 지양

### 임포트 순서
- 표준 라이브러리 → 서드파티 → 로컬 임포트

### RAG/임베딩
- ChromaDB 컬렉션 관리
- 청킹 전략 명확히
- 임베딩 모델 일관성

## Frontend (JavaScript/TypeScript)

### TypeScript
- strict mode 권장

### React 패턴
- 함수형 컴포넌트
- hooks 사용
- key prop 필수 (lists)
