"""bootstrap 진입점 스크립트 공용 헬퍼.

`export_meta.py` / `create_tables.py` / `insert_data.py` 가 동일하게
필요로 하던 `_venv_python` 을 한 곳에 모은다 — 각자 .venv python 경로 결정
로직을 복사해두면 backend 디렉터리 구조 변경 시 세 곳을 동시에 손대야 한다.
"""

from __future__ import annotations

import os
from pathlib import Path


def _venv_python(project_dir: Path) -> str:
    """프로젝트의 .venv python 실행파일 경로를 반환.

    .venv 가 누락되어 있으면 ``RuntimeError`` 를 던져 호출자(orchestrator)가
    즉시 실패하도록 한다 — ``sys.executable`` 로 silent 폴백하면 backend 별로
    분리된 의존성(예: asyncpg vs psycopg2)이 깨진 채로 진행되어 진단이
    어려운 런타임 오류로 이어진다.
    """
    if os.name == "nt":
        candidate = project_dir / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = project_dir / ".venv" / "bin" / "python"
    if not candidate.exists():
        raise RuntimeError(
            f"{project_dir} 의 .venv python 을 찾을 수 없습니다 "
            f"(기대 경로: {candidate}). 해당 backend 의 .venv 를 먼저 생성하세요."
        )
    return str(candidate)
