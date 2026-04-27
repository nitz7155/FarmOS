"""AI Agent decisions 시드 (Design Ref §8.6 - L2/L3 E2E 테스트용 30건 샘플).

`bootstrap/insert_data.py`(Phase 2) 가 `seed_ai_agent()` 를 호출한다.

멱등성:
- `ai_agent_decisions` id 는 루프 인덱스 ``i`` 로부터 ``uuid5`` 로 결정되므로
  같은 ``i`` 는 매번 같은 id 를 produce → `INSERT ... ON CONFLICT (id) DO NOTHING`
  가 실제로 작동한다 (이전엔 ``uuid4`` 라 매 실행마다 30건이 누적됐다).
- 결과적으로 `ai_agent_activity_daily/hourly` 의 누적 UPSERT 도 같이 멱등 —
  decisions 가 conflict 면 ``result.rowcount == 0`` 분기로 요약 갱신도 건너뛴다.
- 추가 안전장치로 함수 시작 시 row 수가 목표(``count``) 이상이면 early return
  (`shoppingmall_review_seed` 와 동일한 패턴 — 60+회 SQL 호출을 절약).
"""

# ruff: noqa: E402
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# app 모듈 접근 위해 backend/ 를 sys.path 에 추가
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from app.core.database import async_session

CONTROL_TYPES = ["ventilation", "irrigation", "lighting", "shading"]
PRIORITIES = ["emergency", "high", "medium", "low"]
SOURCES = ["rule", "llm", "tool", "manual"]

REASONS = {
    "ventilation": [
        "CO2 450ppm, 내부 29도 → 창문 60% 개방",
        "외기 대비 내부 습도 85% → 팬 가속",
        "일몰 후 야간 환기 모드 전환",
    ],
    "irrigation": [
        "토양수분 52% — 임계값 이하 → 밸브 열림",
        "작물 흡수량 예측 기반 20분 관수",
        "N:P:K 비율 재조정 (1.2 : 1.0 : 0.8)",
    ],
    "lighting": [
        "조도 18000lux 부족 → 보조등 점등",
        "일출 이후 보조광 OFF",
        "개화 촉진 광주기 조정",
    ],
    "shading": [
        "오후 2시 강일사 → 차광막 40%",
        "야간 온도 저하 예보 → 보온커튼 70%",
        "흐림 전환 → 차광 해제",
    ],
}

DEFAULT_DECISION_COUNT = 30

# ai_agent 시드 전용 고정 namespace — uuid5 입력으로 i 만 들어가면 같은 결과를 보장.
# 실 운영 Relay 가 생성하는 임의 UUID v4 와 충돌할 확률은 무시 가능 (uuid5 는 다른 비트 패턴).
SEED_NAMESPACE = uuid.UUID("a1f4c8e0-7b3d-4e9a-9c5f-1d8b6e0a3c2f")


def _make_decision(now: datetime, i: int) -> dict:
    ct = CONTROL_TYPES[i % 4]
    pr = PRIORITIES[i % 4]
    src = SOURCES[i % 4]
    ts = now - timedelta(minutes=i * 17)  # 과거로 분산
    reasons = REASONS[ct]
    return {
        "id": str(uuid.uuid5(SEED_NAMESPACE, f"ai-agent-decision-{i}")),
        "timestamp": ts,
        "control_type": ct,
        "priority": pr,
        "source": src,
        "reason": reasons[i % len(reasons)],
        "action": {
            "ventilation": {"window_open_pct": 50 + (i % 5) * 10, "fan_speed": 800 + i * 20},
            "irrigation": {"valve_open": True, "duration_s": 60 + i * 10},
            "lighting": {"on": True, "brightness_pct": 60 + (i % 4) * 10},
            "shading": {"shade_pct": 30 + (i % 5) * 10, "insulation_pct": 0},
        }[ct],
        "tool_calls": [
            {
                "tool": {
                    "ventilation": "open_window",
                    "irrigation": "open_valve",
                    "lighting": "set_brightness",
                    "shading": "set_shade",
                }[ct],
                "arguments": {"pct": 50 + (i % 5) * 10},
                "result": {"success": (i % 7 != 0)},  # 가끔 실패 행 섞기
            }
        ],
        "sensor_snapshot": {
            "temperature": round(22.0 + (i % 10) * 0.8, 1),
            "humidity": 55 + (i % 15),
            "light_intensity": 15000 + i * 400,
            "soil_moisture": round(50.0 + (i % 8) * 1.5, 1),
            "timestamp": ts.isoformat(),
        },
        "duration_ms": 200 + (i * 17) % 600,
    }


async def seed_ai_agent(count: int = DEFAULT_DECISION_COUNT) -> tuple[int, int]:
    """AI Agent decisions 더미 데이터를 생성/적재한다.

    `ai_agent_decisions` 테이블에 deterministic id(uuid5) 로
    `INSERT ... ON CONFLICT (id) DO NOTHING` 적재하고, `ai_agent_activity_daily/hourly`
    집계를 UPSERT 한다.

    멱등성: 같은 ``i`` 는 같은 id 를 produce 하므로 재실행해도 row 가 누적되지 않는다.
    추가로 시작 시점에 row 수가 ``count`` 이상이면 즉시 return (review_seed 패턴).

    이 함수는 테이블이 이미 존재한다고 가정한다(Phase 1 에서 만들어졌어야 함).

    Returns:
        (inserted_decisions, summary_bumps) 튜플.
    """
    now = datetime.now(timezone.utc)

    inserted_decisions = 0
    summary_bumps = 0

    async with async_session() as db:
        existing_count = (
            await db.execute(text("SELECT COUNT(*) FROM ai_agent_decisions"))
        ).scalar_one() or 0
        if existing_count >= count:
            # 이미 충분히 시드된 상태 — 30+ 회의 INSERT/UPSERT SQL 을 통째로 스킵.
            return 0, 0

        for i in range(count):
            d = _make_decision(now, i)

            # duration_ms 가 None 일 때 평균 분모/분자에서 제외하기 위한 사전 계산.
            # asyncpg prepared statement 가 동일 파라미터를 여러 컨텍스트(IS NULL/산술)에서
            # 쓰면 타입 추론에 실패(AmbiguousParameterError)하므로 SQL 에는 항상 정수만 넘긴다.
            dur_value = d["duration_ms"]
            dur_inc = 0 if dur_value is None else 1
            dur_add = 0 if dur_value is None else dur_value

            # 1) 원본 insert — id 가 i 로부터 deterministic(uuid5) 이라 ON CONFLICT 가 실제 작동.
            #    rowcount == 0 (이미 존재) 이면 아래 daily/hourly UPSERT 도 함께 건너뛴다.
            result = await db.execute(
                text(
                    """
                    INSERT INTO ai_agent_decisions
                        (id, timestamp, control_type, priority, source, reason,
                         action, tool_calls, sensor_snapshot, duration_ms, created_at)
                    VALUES
                        (:id, :ts, :ct, :pr, :src, :reason,
                         CAST(:action AS jsonb), CAST(:tool_calls AS jsonb),
                         CAST(:snapshot AS jsonb), :dur, now())
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": d["id"],
                    "ts": d["timestamp"],
                    "ct": d["control_type"],
                    "pr": d["priority"],
                    "src": d["source"],
                    "reason": d["reason"],
                    "action": json.dumps(d["action"]),
                    "tool_calls": json.dumps(d["tool_calls"]),
                    "snapshot": json.dumps(d["sensor_snapshot"]),
                    "dur": d["duration_ms"],
                },
            )
            if result.rowcount == 0:
                continue  # 이미 존재
            inserted_decisions += 1

            # 2) 일별 집계 UPSERT
            # avg_duration_ms 는 duration_sum / duration_count 의 캐시값.
            # null-duration 행은 분모/분자에서 모두 제외되어 편향이 없다 (모델 docstring 참고).
            await db.execute(
                text(
                    """
                    INSERT INTO ai_agent_activity_daily
                        (day, control_type, count, by_source, by_priority,
                         avg_duration_ms, duration_count, duration_sum,
                         last_at, updated_at)
                    VALUES
                        (:day, :ct, 1,
                         jsonb_build_object(CAST(:src AS text), 1),
                         jsonb_build_object(CAST(:pr AS text), 1),
                         CAST(:avg_dur AS integer), :dur_inc, :dur_add,
                         :last_at, now())
                    ON CONFLICT (day, control_type) DO UPDATE SET
                        count = ai_agent_activity_daily.count + 1,
                        by_source = jsonb_set(
                            ai_agent_activity_daily.by_source,
                            ARRAY[CAST(:src AS text)],
                            to_jsonb(COALESCE((ai_agent_activity_daily.by_source->>:src)::int, 0) + 1)
                        ),
                        by_priority = jsonb_set(
                            ai_agent_activity_daily.by_priority,
                            ARRAY[CAST(:pr AS text)],
                            to_jsonb(COALESCE((ai_agent_activity_daily.by_priority->>:pr)::int, 0) + 1)
                        ),
                        duration_count = ai_agent_activity_daily.duration_count + :dur_inc,
                        duration_sum = ai_agent_activity_daily.duration_sum + :dur_add,
                        avg_duration_ms = CASE
                            WHEN ai_agent_activity_daily.duration_count + :dur_inc = 0 THEN NULL
                            ELSE (ai_agent_activity_daily.duration_sum + :dur_add)
                                 / (ai_agent_activity_daily.duration_count + :dur_inc)
                        END,
                        last_at = GREATEST(ai_agent_activity_daily.last_at, :last_at),
                        updated_at = now()
                    """
                ),
                {
                    "day": d["timestamp"].date(),
                    "ct": d["control_type"],
                    "src": d["source"],
                    "pr": d["priority"],
                    "avg_dur": dur_value,
                    "dur_inc": dur_inc,
                    "dur_add": dur_add,
                    "last_at": d["timestamp"],
                },
            )

            # 3) 시간별 집계 UPSERT
            hour_bucket = d["timestamp"].replace(minute=0, second=0, microsecond=0)
            await db.execute(
                text(
                    """
                    INSERT INTO ai_agent_activity_hourly
                        (hour, control_type, count, by_source, by_priority, last_at, updated_at)
                    VALUES
                        (:hour, :ct, 1,
                         jsonb_build_object(CAST(:src AS text), 1),
                         jsonb_build_object(CAST(:pr AS text), 1),
                         :last_at, now())
                    ON CONFLICT (hour, control_type) DO UPDATE SET
                        count = ai_agent_activity_hourly.count + 1,
                        by_source = jsonb_set(
                            ai_agent_activity_hourly.by_source,
                            ARRAY[CAST(:src AS text)],
                            to_jsonb(COALESCE((ai_agent_activity_hourly.by_source->>:src)::int, 0) + 1)
                        ),
                        by_priority = jsonb_set(
                            ai_agent_activity_hourly.by_priority,
                            ARRAY[CAST(:pr AS text)],
                            to_jsonb(COALESCE((ai_agent_activity_hourly.by_priority->>:pr)::int, 0) + 1)
                        ),
                        last_at = GREATEST(ai_agent_activity_hourly.last_at, :last_at),
                        updated_at = now()
                    """
                ),
                {
                    "hour": hour_bucket,
                    "ct": d["control_type"],
                    "src": d["source"],
                    "pr": d["priority"],
                    "last_at": d["timestamp"],
                },
            )
            summary_bumps += 1

        await db.commit()

    return inserted_decisions, summary_bumps
