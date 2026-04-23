"""일일 통합 영농일지(DailyJournal) 모델.

하루 동안 쌓인 여러 개별 `JournalEntry`를 LLM이 한 편의 서술형 문서로 통합한
"완성품"에 해당한다. 농업ON 양식에 가까운 최종 보고서 용도이며,
`JournalEntry`는 그대로 두고 이 테이블은 별도 관리한다.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Integer,
    String,
    Date,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DailyJournal(Base):
    """하루 1건의 통합 영농일지 (draft → confirmed)."""

    __tablename__ = "daily_journals"
    __table_args__ = (
        UniqueConstraint("user_id", "work_date", name="uq_daily_journal_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("users.id"), nullable=False
    )

    # ── 핵심 ──
    work_date: Mapped[date] = mapped_column(Date, nullable=False)

    # "draft" | "confirmed"
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)

    # LLM이 생성했거나 유저가 편집한 서술형 본문 (마크다운 아님, 순수 텍스트)
    narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # "llm" | "llm_edited" | "manual" | "template_fallback"
    narrative_source: Mapped[str] = mapped_column(
        String(20), default="llm", nullable=False
    )

    # ── 원본 추적 ──

    # 통합에 사용된 JournalEntry id 배열
    source_entry_ids: Mapped[list[int]] = mapped_column(JSON, default=list)

    # 생성 시점 entry들의 직렬화 스냅샷.
    # 원본이 나중에 수정/삭제되어도 생성 근거를 재현할 수 있게 보존.
    entry_snapshot: Mapped[list[dict]] = mapped_column(JSON, default=list)

    # ── 메타 ──

    llm_model: Mapped[str | None] = mapped_column(String(100), default=None)
    llm_prompt_version: Mapped[str | None] = mapped_column(String(20), default=None)

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── 관계 ──

    revisions: Mapped[list["DailyJournalRevision"]] = relationship(
        "DailyJournalRevision",
        back_populates="daily_journal",
        cascade="all, delete-orphan",
        order_by="DailyJournalRevision.created_at.desc()",
    )


class DailyJournalRevision(Base):
    """DailyJournal 본문의 이전 버전 스냅샷 (편집/재생성 히스토리)."""

    __tablename__ = "daily_journal_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # PostgreSQL은 FK 컬럼에 자동 인덱스를 만들지 않으므로 명시적으로 지정.
    # revisions 관계 로드 / `GET /{dj_id}/revisions` 모두 이 컬럼으로 조회.
    daily_journal_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("daily_journals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_source: Mapped[str] = mapped_column(
        String(20), default="llm", nullable=False
    )

    # 편집자 user_id (추후 팀 기능 대비). 자기 자신이 편집한 경우 자신의 id.
    created_by: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("users.id"), default=None
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    daily_journal: Mapped["DailyJournal"] = relationship(
        "DailyJournal", back_populates="revisions"
    )
