"""일일 통합 영농일지(DailyJournal) Pydantic 스키마."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


NARRATIVE_SOURCE = Literal["llm", "llm_edited", "manual", "template_fallback"]
DAILY_JOURNAL_STATUS = Literal["draft", "confirmed"]


# ── 요청 ──


class DailyJournalGenerateRequest(BaseModel):
    """오늘(또는 지정일)의 JournalEntry들을 LLM으로 통합하여 생성."""

    work_date: date

    # 특정 entry만 포함하고 싶을 때 사용 (미지정 시 해당 날짜 전체).
    entry_ids: list[int] | None = None

    # 이미 draft가 존재할 때 기존 본문을 revision으로 밀어내고 새로 생성할지 여부.
    # False(기본)이고 draft가 이미 있으면 409 에러 반환 → 유저가 재생성 의사 명시하도록.
    overwrite: bool = False


class DailyJournalUpdateRequest(BaseModel):
    """서술형 본문 편집 요청. confirmed 상태에서는 거부."""

    # strip_whitespace=True로 공백-only 값 차단 (순수 min_length=1은 "   " 통과).
    narrative: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=20000),
    ]

    # "llm_edited" (LLM 결과를 일부 손본 경우) / "manual" (처음부터 직접 작성)
    narrative_source: Literal["llm_edited", "manual"] = "llm_edited"


# ── 응답 ──


class DailyJournalRevisionResponse(BaseModel):
    """편집 히스토리 1건."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    narrative: str
    narrative_source: str
    created_by: str | None
    created_at: datetime


class DailyJournalResponse(BaseModel):
    """DailyJournal 단건 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    work_date: date
    status: DAILY_JOURNAL_STATUS
    narrative: str
    narrative_source: NARRATIVE_SOURCE

    source_entry_ids: list[int] = []
    entry_snapshot: list[dict] = []

    llm_model: str | None = None
    llm_prompt_version: str | None = None

    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # include_revisions=true 일 때만 채워짐.
    revisions: list[DailyJournalRevisionResponse] | None = None


class DailyJournalListResponse(BaseModel):
    """목록 응답 (월/기간 단위 조회용)."""

    items: list[DailyJournalResponse]
    total: int
