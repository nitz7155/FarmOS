"""일일 통합 영농일지(DailyJournal) CRUD & 비즈니스 로직."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.daily_journal_composer import compose_daily_journal
from app.models.daily_journal import DailyJournal, DailyJournalRevision
from app.models.journal import JournalEntry


class DailyJournalError(Exception):
    """DailyJournal 처리 도메인 에러 (라우터에서 HTTPException으로 매핑)."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# ── 조회 ──


async def get_by_id(
    db: AsyncSession, user_id: str, dj_id: int, include_revisions: bool = False
) -> DailyJournal | None:
    q = select(DailyJournal).where(
        DailyJournal.id == dj_id, DailyJournal.user_id == user_id
    )
    if include_revisions:
        q = q.options(selectinload(DailyJournal.revisions))
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def get_by_date(
    db: AsyncSession, user_id: str, work_date: date
) -> DailyJournal | None:
    result = await db.execute(
        select(DailyJournal).where(
            DailyJournal.user_id == user_id,
            DailyJournal.work_date == work_date,
        )
    )
    return result.scalar_one_or_none()


async def list_in_range(
    db: AsyncSession,
    user_id: str,
    date_from: date,
    date_to: date,
) -> list[DailyJournal]:
    """기간 내 모든 DailyJournal을 작업일 오름차순으로 반환."""
    result = await db.execute(
        select(DailyJournal)
        .where(
            DailyJournal.user_id == user_id,
            DailyJournal.work_date >= date_from,
            DailyJournal.work_date <= date_to,
        )
        .order_by(DailyJournal.work_date.asc())
    )
    return list(result.scalars().all())


# ── 원본 entry 수집 ──


async def _load_source_entries(
    db: AsyncSession,
    user_id: str,
    work_date: date,
    entry_ids: list[int] | None,
) -> list[JournalEntry]:
    q = select(JournalEntry).where(
        JournalEntry.user_id == user_id,
        JournalEntry.work_date == work_date,
    )
    if entry_ids:
        q = q.where(JournalEntry.id.in_(entry_ids))
    q = q.order_by(JournalEntry.created_at.asc(), JournalEntry.id.asc())
    result = await db.execute(q)
    return list(result.scalars().all())


def _snapshot_entry(e: JournalEntry) -> dict:
    """원본 entry의 생성 시점 스냅샷 (JSON 직렬화 가능 형태)."""
    return {
        "id": e.id,
        "work_date": e.work_date.isoformat() if e.work_date else None,
        "field_name": e.field_name,
        "crop": e.crop,
        "work_stage": e.work_stage,
        "weather": e.weather,
        "usage_pesticide_type": e.usage_pesticide_type,
        "usage_pesticide_product": e.usage_pesticide_product,
        "usage_pesticide_amount": e.usage_pesticide_amount,
        "usage_fertilizer_type": e.usage_fertilizer_type,
        "usage_fertilizer_product": e.usage_fertilizer_product,
        "usage_fertilizer_amount": e.usage_fertilizer_amount,
        "purchase_pesticide_type": e.purchase_pesticide_type,
        "purchase_pesticide_product": e.purchase_pesticide_product,
        "purchase_pesticide_amount": e.purchase_pesticide_amount,
        "purchase_fertilizer_type": e.purchase_fertilizer_type,
        "purchase_fertilizer_product": e.purchase_fertilizer_product,
        "purchase_fertilizer_amount": e.purchase_fertilizer_amount,
        "detail": e.detail,
        "source": e.source,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ── revision 기록 헬퍼 ──


def _push_revision(db: AsyncSession, dj: DailyJournal, created_by: str | None) -> None:
    """현재 본문을 revision 테이블로 스냅샷.

    caller가 commit을 책임진다. 세션에 add만 하고 flush는 하지 않는다.
    """
    rev = DailyJournalRevision(
        daily_journal_id=dj.id,
        narrative=dj.narrative,
        narrative_source=dj.narrative_source,
        created_by=created_by,
    )
    db.add(rev)


# ── 생성/재생성 ──


async def generate(
    db: AsyncSession,
    user_id: str,
    work_date: date,
    entry_ids: list[int] | None = None,
    overwrite: bool = False,
    farm_name: str | None = None,
) -> DailyJournal:
    """해당 날짜 entry들을 통합하여 DailyJournal 생성/재생성.

    규칙:
    - 해당 날짜에 draft DJ가 이미 존재하고 overwrite=False → 409.
    - draft가 있고 overwrite=True → 기존 본문을 revision으로 보존 후 갱신.
    - confirmed 상태는 재생성 불가 → 409.
    - 해당 날짜에 entry가 하나도 없으면 → 400.
    """
    entries = await _load_source_entries(db, user_id, work_date, entry_ids)
    if not entries:
        raise DailyJournalError(
            "no_entries",
            f"{work_date.isoformat()}에 기록된 영농일지(entry)가 없습니다.",
            status=400,
        )

    # entry_ids가 지정된 경우, 요청한 ID가 모두 해당 날짜·유저에 속하는지 검증.
    # 일부만 매칭되면 사용자가 의도한 기록이 PDF에서 조용히 누락될 수 있어 명시적으로 실패.
    if entry_ids:
        found_ids = {e.id for e in entries}
        missing_ids = [eid for eid in entry_ids if eid not in found_ids]
        if missing_ids:
            raise DailyJournalError(
                "invalid_entry_ids",
                f"요청한 entry_ids 중 {len(missing_ids)}건이 "
                f"{work_date.isoformat()}의 본인 영농일지에 없습니다: {missing_ids}",
                status=400,
            )

    existing = await get_by_date(db, user_id, work_date)

    if existing is not None:
        if existing.status == "confirmed":
            raise DailyJournalError(
                "already_confirmed",
                "이미 확정된 일일 영농일지는 재생성할 수 없습니다. 먼저 확정을 해제하세요.",
                status=409,
            )
        if not overwrite:
            raise DailyJournalError(
                "already_exists",
                "해당 날짜의 draft가 이미 존재합니다. overwrite=true로 재생성하세요.",
                status=409,
            )

    composed = await compose_daily_journal(
        entries=entries,
        target_date=work_date,
        farm_name=farm_name,
    )
    snapshot = [_snapshot_entry(e) for e in entries]
    source_ids = [e.id for e in entries]

    if existing is None:
        dj = DailyJournal(
            user_id=user_id,
            work_date=work_date,
            status="draft",
            narrative=composed["narrative"],
            narrative_source=composed["narrative_source"],
            source_entry_ids=source_ids,
            entry_snapshot=snapshot,
            llm_model=composed["llm_model"],
            llm_prompt_version=composed["llm_prompt_version"],
        )
        db.add(dj)
        try:
            await db.commit()
        except IntegrityError as exc:
            # TOCTOU: get_by_date 확인 이후 LLM 호출이 긴 동안 동시 요청이 먼저 insert한 경우.
            # UNIQUE(user_id, work_date) 위반 → 도메인 409로 매핑 (프론트는 기존 것 자동 로드).
            await db.rollback()
            raise DailyJournalError(
                "already_exists",
                "다른 요청이 먼저 해당 날짜의 통합 영농일지를 생성했습니다. "
                "잠시 후 다시 확인해주세요.",
                status=409,
            ) from exc
        await db.refresh(dj)
        return dj

    # overwrite 경로: 기존 본문을 revision으로 밀어내고 덮어쓴다.
    _push_revision(db, existing, created_by=user_id)
    existing.narrative = composed["narrative"]
    existing.narrative_source = composed["narrative_source"]
    existing.source_entry_ids = source_ids
    existing.entry_snapshot = snapshot
    existing.llm_model = composed["llm_model"]
    existing.llm_prompt_version = composed["llm_prompt_version"]
    existing.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(existing)
    return existing


# ── 편집/확정 ──


async def update_narrative(
    db: AsyncSession,
    user_id: str,
    dj_id: int,
    new_narrative: str,
    narrative_source: str = "llm_edited",
) -> DailyJournal:
    """서술형 본문 편집. 기존 본문은 revision으로 보존.

    confirmed 상태에서는 거부.
    """
    dj = await get_by_id(db, user_id, dj_id)
    if dj is None:
        raise DailyJournalError("not_found", "일일 영농일지를 찾을 수 없습니다.", status=404)
    if dj.status == "confirmed":
        raise DailyJournalError(
            "already_confirmed",
            "확정된 일일 영농일지는 편집할 수 없습니다. 먼저 확정을 해제하세요.",
            status=409,
        )

    # 변화가 없으면 revision을 남기지 않는다.
    if new_narrative.strip() == (dj.narrative or "").strip():
        return dj

    _push_revision(db, dj, created_by=user_id)
    dj.narrative = new_narrative
    dj.narrative_source = narrative_source
    dj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dj)
    return dj


async def confirm(db: AsyncSession, user_id: str, dj_id: int) -> DailyJournal:
    """draft → confirmed. 멱등적이지 않음 (이미 confirmed면 409)."""
    dj = await get_by_id(db, user_id, dj_id)
    if dj is None:
        raise DailyJournalError("not_found", "일일 영농일지를 찾을 수 없습니다.", status=404)
    if dj.status == "confirmed":
        raise DailyJournalError(
            "already_confirmed", "이미 확정된 일일 영농일지입니다.", status=409
        )
    dj.status = "confirmed"
    dj.confirmed_at = datetime.now(timezone.utc)
    dj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dj)
    return dj


async def unconfirm(db: AsyncSession, user_id: str, dj_id: int) -> DailyJournal:
    """confirmed → draft 로 되돌린다."""
    dj = await get_by_id(db, user_id, dj_id)
    if dj is None:
        raise DailyJournalError("not_found", "일일 영농일지를 찾을 수 없습니다.", status=404)
    if dj.status != "confirmed":
        raise DailyJournalError(
            "not_confirmed", "확정 상태가 아닙니다.", status=409
        )
    dj.status = "draft"
    dj.confirmed_at = None
    dj.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(dj)
    return dj


async def list_revisions(
    db: AsyncSession, user_id: str, dj_id: int
) -> list[DailyJournalRevision]:
    """편집 히스토리 목록 (최신순)."""
    dj = await get_by_id(db, user_id, dj_id, include_revisions=True)
    if dj is None:
        raise DailyJournalError("not_found", "일일 영농일지를 찾을 수 없습니다.", status=404)
    # relationship의 order_by가 desc로 걸려있어 그대로 반환.
    return list(dj.revisions)
