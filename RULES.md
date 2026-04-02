# 코딩 컨벤션

## 개요

FarmOS 프로젝트의 모든 코드 변경사항은 다음 규칙을 **자동으로 검증 및 적용**합니다.

Claude Code가 이 문서를 읽고 자동으로 hooks를 설정하여, IDE에서 파일을 저장하는 순간 컨벤션이 적용됩니다.

---

## 규칙

### Backend (Python)

**도구:** Ruff
- **포매팅**: 자동 코드 포맷팅
- **린팅**: 린팅 규칙 자동 수정
- **실행 시점**: 파일 저장 시 (Claude Code hooks)

### Frontend (TypeScript/React)

**도구:** ESLint + Prettier
- **Prettier**: 자동 코드 포매팅
- **ESLint**: ESLint 9.x + TypeScript ESLint 규칙 준수 + React Hooks 플러그인
- **실행 시점**: 파일 저장 시 (Claude Code hooks)

---

## 자동화 (Claude Code Hooks)

모든 규칙은 **Claude Code의 hooks를 통해 자동으로 실행**됩니다.

### 동작 원리

1. Claude Code에서 코드 작성/수정
2. 파일 저장 (Write/Edit)
3. **자동 실행:**
   - Backend 파일: Ruff 포매팅 → Ruff 린팅
   - Frontend 파일: Prettier 포매팅 → ESLint 자동 수정
4. 포맷팅된 파일 저장 완료

### 특징

- 수동 작업 불필요 (저장하면 자동 적용)
- IDE와 무관하게 Claude Code에서만 자동 실행
- 개발자는 컨벤션 신경 쓰지 않고 개발 집중 가능

---

## 온보딩 (초기 설정)

### 1단계: 프로젝트 클론

```bash
git clone <repository>
cd FarmOS
```

### 2단계: Claude Code 열기

프로젝트 루트에서 Claude Code를 실행합니다:

```bash
claude
```

### 3단계: 완료

Claude Code가 **RULES.md를 자동으로 읽고** hooks를 설정합니다.

이제 IDE에서 파일을 저장할 때마다 Ruff (Backend) + Prettier + ESLint (Frontend)가 자동으로 실행됩니다.

---

## 수동 실행 (필요 시)

개발 중 수동으로 실행해야 할 경우:

### Backend (Python)

```bash
cd backend

# Ruff로 포매팅 + 린팅 (전체)
uv run ruff format .
uv run ruff check --fix .

# Ruff로 포매팅 (특정 파일)
uv run ruff format app/api/auth.py

# Ruff로 린팅 확인
uv run ruff check .

# Ruff로 자동 수정
uv run ruff check --fix .
```

### Frontend (TypeScript/React)

```bash
cd frontend

# Prettier로 포매팅 (전체)
npm run format

# Prettier로 포매팅 (특정 파일)
npx prettier --write src/components/Button.tsx

# ESLint 실행
npm run lint

# ESLint 자동 수정
npm run lint -- --fix
```

---

## 파일 참고

- **RULES.md** (이 파일): 컨벤션 규칙 정의
- **backend/pyproject.toml**: Backend 의존성 설정
- **frontend/package.json**: Frontend 의존성 및 scripts 설정
- **frontend/eslint.config.js**: Frontend 린팅 설정
