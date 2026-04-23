"""일일 통합 영농일지(DailyJournal) API 라우터."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core import daily_journal_store
from app.core.daily_journal_pdf import (
    generate_daily_journal_pdf,
    generate_period_pdf,
)
from app.core.daily_journal_store import DailyJournalError
from app.models.user import User
from app.schemas.daily_journal import (
    DailyJournalGenerateRequest,
    DailyJournalResponse,
    DailyJournalRevisionResponse,
    DailyJournalUpdateRequest,
)


router = APIRouter(prefix="/daily-journal", tags=["daily-journal"])


def _to_response(dj, include_revisions: bool = False) -> DailyJournalResponse:
    """ORM → Pydantic 변환. revisions 포함 여부를 제어.

    `model_validate(dj, from_attributes=True)`는 모든 필드를 getattr로 접근하는데,
    `revisions`는 SQLAlchemy async relationship이라 커밋 이후 lazy-load가
    sync 컨텍스트에서 시도되면 MissingGreenlet으로 터진다.
    그래서 필드를 명시적으로 dict로 뽑아 lazy-load를 원천 차단한다.
    """
    data: dict = {
        "id": dj.id,
        "user_id": dj.user_id,
        "work_date": dj.work_date,
        "status": dj.status,
        "narrative": dj.narrative,
        "narrative_source": dj.narrative_source,
        "source_entry_ids": dj.source_entry_ids or [],
        "entry_snapshot": dj.entry_snapshot or [],
        "llm_model": dj.llm_model,
        "llm_prompt_version": dj.llm_prompt_version,
        "confirmed_at": dj.confirmed_at,
        "created_at": dj.created_at,
        "updated_at": dj.updated_at,
        "revisions": None,
    }
    if include_revisions:
        # caller가 include_revisions=True로 부를 때는 이미 selectinload로
        # revisions를 로드한 상태라는 계약. 여기서 순회는 lazy-load 없이 안전.
        data["revisions"] = [
            {
                "id": r.id,
                "narrative": r.narrative,
                "narrative_source": r.narrative_source,
                "created_by": r.created_by,
                "created_at": r.created_at,
            }
            for r in dj.revisions
        ]
    return DailyJournalResponse.model_validate(data)


@router.post("/generate", response_model=DailyJournalResponse, status_code=201)
async def generate_daily_journal(
    body: DailyJournalGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """해당 날짜의 JournalEntry들을 LLM으로 통합하여 DailyJournal draft 생성.

    - 해당 날짜에 entry가 없으면 400.
    - 이미 draft가 있고 overwrite=false면 409 (의도적 재생성 요구).
    - confirmed 상태면 항상 409.
    """
    try:
        dj = await daily_journal_store.generate(
            db=db,
            user_id=current_user.id,
            work_date=body.work_date,
            entry_ids=body.entry_ids,
            overwrite=body.overwrite,
            farm_name=current_user.farmname or current_user.name,
        )
    except DailyJournalError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
        ) from e
    return _to_response(dj)


@router.get("", response_model=DailyJournalResponse | None)
async def get_daily_journal_by_date(
    target_date: date = Query(..., alias="date"),
    include_revisions: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 날짜의 DailyJournal 조회.

    "해당 날짜에 통합본이 아직 없음"은 에러가 아닌 정상 상태이므로
    404가 아닌 **200 + null** 로 응답한다 (브라우저 콘솔 에러 방지).
    ID로 조회하는 `GET /{dj_id}`는 기존대로 404 유지.
    """
    dj = await daily_journal_store.get_by_date(db, current_user.id, target_date)
    if dj is None:
        return None
    if include_revisions:
        # revisions 관계 로드
        dj = await daily_journal_store.get_by_id(
            db, current_user.id, dj.id, include_revisions=True
        )
    return _to_response(dj, include_revisions=include_revisions)


@router.get("/export-pdf")
async def export_period_pdf(
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """기간 내 모든 통합 영농일지를 한 PDF에 묶어서 내보낸다.

    - 통합본이 없는 날짜는 skip (자동 생성하지 않음).
    - 기간 내 통합본이 0건이면 빈 안내 페이지 1매.
    """
    if date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail="date_from은 date_to보다 이후일 수 없습니다.",
        )

    djs = await daily_journal_store.list_in_range(
        db, current_user.id, date_from, date_to
    )
    # PDF 렌더링은 동기 CPU·I/O 작업이라 이벤트 루프 점유 방지를 위해 threadpool로 오프로드.
    pdf_bytes = await run_in_threadpool(
        generate_period_pdf,
        djs,
        farm_name=current_user.farmname or current_user.name or "",
        date_from=date_from,
        date_to=date_to,
    )
    filename = f"daily_journal_{date_from}_{date_to}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{dj_id}", response_model=DailyJournalResponse)
async def get_daily_journal(
    dj_id: int,
    include_revisions: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ID로 DailyJournal 단건 조회."""
    dj = await daily_journal_store.get_by_id(
        db, current_user.id, dj_id, include_revisions=include_revisions
    )
    if dj is None:
        raise HTTPException(404, "일일 영농일지를 찾을 수 없습니다.")
    return _to_response(dj, include_revisions=include_revisions)


@router.patch("/{dj_id}", response_model=DailyJournalResponse)
async def update_daily_journal(
    dj_id: int,
    body: DailyJournalUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """서술형 본문 편집. 기존 본문은 revision으로 자동 보존. confirmed 상태는 거부."""
    try:
        dj = await daily_journal_store.update_narrative(
            db=db,
            user_id=current_user.id,
            dj_id=dj_id,
            new_narrative=body.narrative,
            narrative_source=body.narrative_source,
        )
    except DailyJournalError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
        ) from e
    return _to_response(dj)


@router.post("/{dj_id}/regenerate", response_model=DailyJournalResponse)
async def regenerate_daily_journal(
    dj_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """기존 DailyJournal을 같은 날짜 entry로 재생성. 기존 본문은 revision으로 보존.

    편의 엔드포인트 — 내부적으로 `generate(overwrite=True, work_date=dj.work_date)` 호출.
    """
    dj = await daily_journal_store.get_by_id(db, current_user.id, dj_id)
    if dj is None:
        raise HTTPException(404, "일일 영농일지를 찾을 수 없습니다.")
    try:
        regenerated = await daily_journal_store.generate(
            db=db,
            user_id=current_user.id,
            work_date=dj.work_date,
            entry_ids=None,
            overwrite=True,
            farm_name=current_user.farmname or current_user.name,
        )
    except DailyJournalError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
        ) from e
    return _to_response(regenerated)


@router.post("/{dj_id}/confirm", response_model=DailyJournalResponse)
async def confirm_daily_journal(
    dj_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """draft → confirmed."""
    try:
        dj = await daily_journal_store.confirm(db, current_user.id, dj_id)
    except DailyJournalError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
        ) from e
    return _to_response(dj)


@router.post("/{dj_id}/unconfirm", response_model=DailyJournalResponse)
async def unconfirm_daily_journal(
    dj_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """confirmed → draft 로 되돌린다."""
    try:
        dj = await daily_journal_store.unconfirm(db, current_user.id, dj_id)
    except DailyJournalError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
        ) from e
    return _to_response(dj)


@router.get("/{dj_id}/export-pdf")
async def export_daily_journal_pdf(
    dj_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DailyJournal 서술형 본문 + 원본 부록을 포함한 PDF 내보내기."""
    dj = await daily_journal_store.get_by_id(db, current_user.id, dj_id)
    if dj is None:
        raise HTTPException(404, "일일 영농일지를 찾을 수 없습니다.")

    # PDF 렌더링은 동기 CPU·I/O 작업이라 이벤트 루프 점유 방지를 위해 threadpool로 오프로드.
    pdf_bytes = await run_in_threadpool(
        generate_daily_journal_pdf,
        dj,
        farm_name=current_user.farmname or current_user.name or "",
    )
    filename = f"daily_journal_{dj.work_date.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{dj_id}/revisions", response_model=list[DailyJournalRevisionResponse])
async def list_daily_journal_revisions(
    dj_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """편집 히스토리 목록 (최신순)."""
    try:
        revisions = await daily_journal_store.list_revisions(db, current_user.id, dj_id)
    except DailyJournalError as e:
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
        ) from e
    return [DailyJournalRevisionResponse.model_validate(r) for r in revisions]
