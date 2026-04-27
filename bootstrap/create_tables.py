"""Phase 1 진입점: 빈 테이블 생성 (CREATE TABLE IF NOT EXISTS 의미).

NodeJS 자동화 스크립트가 인자 없이 호출한다:
    python bootstrap/create_tables.py

동작:
1. FarmOS backend venv 로 subprocess 분기 → `init_db()` (FarmOS 코어)
   + pesticide RAG 5개 테이블 `Base.metadata.create_all`.
2. ShoppingMall backend venv 로 subprocess 분기 → ShoppingMall `Base.metadata.create_all`.

`backend/app/` 와 `shopping_mall/backend/app/` 가 같은 패키지명 `app` 을 쓰고
의존 패키지(asyncpg vs psycopg2 등)도 분리되어 있어 한 프로세스에서 직접 import 가
불가능하다 — 그래서 각 backend 의 `.venv` 로 subprocess 분기한다.

원칙:
- 가산형(additive) — 기존 테이블/데이터 보존, 누락분만 추가.
- 컬럼 ALTER 는 수행하지 않는다(데이터 손실 위험; drift 는 NodeJS 가 경고).
- 데이터 INSERT 0건.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from _venv_utils import _venv_python

ROOT = Path(__file__).resolve().parents[1]
FARMOS_BACKEND = ROOT / "backend"
SHOP_BACKEND = ROOT / "shopping_mall" / "backend"


def _run_python_code(label: str, python_exe: str, cwd: Path, code: str) -> None:
    print(f"[create_tables] {label} 시작 (python={python_exe})")
    env = os.environ.copy()
    pythonpath_parts = [str(ROOT)]
    if existing := env.get("PYTHONPATH"):
        pythonpath_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    # 자식 Python 의 stdout/stderr 를 UTF-8 로 강제 (Windows 콘솔 cp949 회피)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run([python_exe, "-c", code], cwd=str(cwd), env=env)
    if result.returncode != 0:
        print(
            f"[create_tables] {label} 실패 (exit={result.returncode})",
            file=sys.stderr,
        )
        raise SystemExit(result.returncode)
    print(f"[create_tables] {label} 완료")


FARMOS_CREATE_CODE = """
import asyncio
import bootstrap.farmos_seed  # noqa: F401  (FarmOS 모델을 Base.metadata 에 등록)
from bootstrap.pesticide import Base as PesticideBase
from app.core.database import close_db, engine, init_db


async def _run() -> None:
    # FarmOS 코어 + 리뷰분석 + NCPMS + AI Agent 등 Base.metadata.create_all
    await init_db()

    # 농약 RAG 5개 테이블 (별도 Base) — async engine 위에서 sync DDL 실행
    async with engine.begin() as conn:
        await conn.run_sync(PesticideBase.metadata.create_all)

    await close_db()


asyncio.run(_run())
"""

SHOP_CREATE_CODE = """
import bootstrap.shoppingmall_seed  # noqa: F401  (ShoppingMall 모델 등록)
from app.database import Base, engine

Base.metadata.create_all(bind=engine)
engine.dispose()
"""


def main() -> int:
    print("[create_tables] Phase 1 시작 (빈 테이블 생성, 멱등)")

    _run_python_code(
        "FarmOS 코어 + 농약 RAG 테이블 생성",
        _venv_python(FARMOS_BACKEND),
        FARMOS_BACKEND,
        FARMOS_CREATE_CODE,
    )

    _run_python_code(
        "ShoppingMall 테이블 생성",
        _venv_python(SHOP_BACKEND),
        SHOP_BACKEND,
        SHOP_CREATE_CODE,
    )

    print("[create_tables] Phase 1 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
