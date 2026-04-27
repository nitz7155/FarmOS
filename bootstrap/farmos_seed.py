"""FarmOS 기본 사용자 시드.

이 모듈은 두 가지 역할을 한다.
1. 모듈 import 시점에 FarmOS 모델을 등록한다(`app.core.database.Base.metadata`).
   `bootstrap/create_tables.py`(Phase 1) 가 import 만 해도
   `Base.metadata.create_all()` 으로 빈 테이블을 만들 수 있다.
2. `seed_farmos_users()` — 기본 테스트 계정을 upsert(멱등) 한다.
   `bootstrap/insert_data.py`(Phase 2) 에서 호출한다.

이 모듈은 어떤 파괴적 동작(DROP/TRUNCATE/DELETE/ALTER)도 수행하지 않는다.
"""

# ruff: noqa: E402
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

# 실행 위치와 무관하게 backend 패키지를 import 할 수 있도록 경로를 보정한다.
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Base.metadata 등록을 위해 모델 모듈을 명시적으로 import 한다.
import app.models.ai_agent  # noqa: F401
import app.models.journal  # noqa: F401
import app.models.review_analysis  # noqa: F401
from app.core.database import async_session
from app.core.security import hash_password
from app.models.user import User

# ======================
# 시드 데이터
# ======================

USER_SEEDS = [
    {
        "id": "farmer01",
        "name": "김사과",
        "email": "farmer01@farmos.kr",
        "password": "farm1234",
        "location": "경북 영주시",
        "area": 33.0,
        "farmname": "김사과 사과농장",
        "profile": "",
    },
    {
        "id": "parkpear",
        "name": "박배나무",
        "email": "parkpear@farmos.kr",
        "password": "pear5678",
        "location": "충남 천안시",
        "area": 25.5,
        "farmname": "박씨네 배 과수원",
        "profile": "",
    },
]

# NodeJS 자동화가 정적 파싱으로 읽는 기대치 (계획 §6 참고)
EXPECTED_ROW_COUNTS = {"users": 2}
POST_PESTICIDE_MIN_ROW_COUNTS = {
    "rag_pesticide_products": 1,
    "rag_pesticide_product_applications": 1,
    "rag_pesticide_documents": 1,
}


async def seed_farmos_users() -> int:
    """FarmOS 기본 테스트 계정을 upsert 한다(이미 있으면 스킵).

    Returns:
        새로 추가된 row 수.
    """
    inserted = 0
    async with async_session() as db:
        for data in USER_SEEDS:
            existing = await db.execute(select(User).where(User.id == data["id"]))
            if existing.scalar_one_or_none():
                continue
            db.add(
                User(
                    id=data["id"],
                    name=data["name"],
                    email=data["email"],
                    password=hash_password(data["password"]),
                    location=data["location"],
                    area=data["area"],
                    farmname=data["farmname"],
                    profile=data["profile"],
                )
            )
            inserted += 1
        await db.commit()
    return inserted
