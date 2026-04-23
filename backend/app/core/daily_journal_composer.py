"""일일 통합 영농일지 본문 생성기.

여러 `JournalEntry`를 입력으로 받아 농업ON 양식에 준하는 "서술형 한 편의 보고서"를
LLM으로 생성한다. 실패 시 기계적 템플릿으로 폴백한다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from app.core.journal_store import check_missing_fields
from app.core.llm_client_base import get_llm_client
from app.core.config import settings
from app.models.journal import JournalEntry


logger = logging.getLogger(__name__)


# 프롬프트 버전 태그 — 프롬프트 수정 시 증가시켜 DB에 기록되게 한다.
PROMPT_VERSION = "v1"

# LLM 프롬프트 크기 방어 상한 (비용·timeout·컨텍스트 오버플로 방지).
# 정상 사용은 하루 5~20건 수준이라 넉넉히 잡되, 극단적인 사례는 soft truncate.
MAX_ENTRIES_IN_PROMPT = 50
MAX_DETAIL_CHARS = 500


SYSTEM_PROMPT = """당신은 한국 농부를 위한 영농일지 작성 보조자입니다.
하루 동안의 작업 기록들을 받아 농업ON 양식에 어울리는 한 편의 서술형 영농일지를 작성합니다.

작성 원칙:
- 시간/작업 순서에 따른 자연스러운 흐름으로 작성한다.
- 작성 톤은 담백한 문어체 (예: "~하였다"). 감정 표현, 과장, 마케팅 표현은 금지.
- 단락 구성 예시:
    1문단) 날짜와 날씨, 전반 개요
    2문단) 필지·작목별 주요 작업 내용 (농약/비료 사용 내역 포함)
    3문단) 관찰 사항 및 특이점 (병해충, 이상 징후 등이 있을 때만)
    4문단) 내일 확인 필요 항목 (선택)
- 누락된 정보가 있으면 "~에 대한 기록이 없음" 형태로 자연스럽게 한 줄 언급한다. 비판적 어조 금지.
- 마크다운 헤더/불릿 금지. 순수 텍스트 문단만 사용. 문단은 빈 줄로 구분.
- 과도한 요약 금지. 실제 기록된 내용을 빠짐없이 반영한다.
- 기록되지 않은 내용은 지어내지 않는다."""


def _format_entry_block(idx: int, e: JournalEntry) -> str:
    """LLM 입력용 단일 엔트리 블록."""
    lines = [f"[#{idx}]"]
    lines.append(f"- 필지: {e.field_name}")
    lines.append(f"- 작목: {e.crop}")
    lines.append(f"- 작업단계: {e.work_stage}")
    if e.weather:
        lines.append(f"- 날씨: {e.weather}")
    # 농약/비료 사용
    if e.usage_pesticide_product or e.usage_pesticide_type:
        amount = f" {e.usage_pesticide_amount}" if e.usage_pesticide_amount else ""
        kind = f"({e.usage_pesticide_type})" if e.usage_pesticide_type else ""
        lines.append(
            f"- 농약 사용: {e.usage_pesticide_product or ''}{amount} {kind}".rstrip()
        )
    if e.usage_fertilizer_product or e.usage_fertilizer_type:
        amount = f" {e.usage_fertilizer_amount}" if e.usage_fertilizer_amount else ""
        kind = f"({e.usage_fertilizer_type})" if e.usage_fertilizer_type else ""
        lines.append(
            f"- 비료 사용: {e.usage_fertilizer_product or ''}{amount} {kind}".rstrip()
        )
    # 구입
    if e.purchase_pesticide_product or e.purchase_pesticide_type:
        amount = f" {e.purchase_pesticide_amount}" if e.purchase_pesticide_amount else ""
        kind = f"({e.purchase_pesticide_type})" if e.purchase_pesticide_type else ""
        lines.append(
            f"- 농약 구입: {e.purchase_pesticide_product or ''}{amount} {kind}".rstrip()
        )
    if e.purchase_fertilizer_product or e.purchase_fertilizer_type:
        amount = f" {e.purchase_fertilizer_amount}" if e.purchase_fertilizer_amount else ""
        kind = f"({e.purchase_fertilizer_type})" if e.purchase_fertilizer_type else ""
        lines.append(
            f"- 비료 구입: {e.purchase_fertilizer_product or ''}{amount} {kind}".rstrip()
        )
    if e.detail:
        # 매우 긴 detail은 프롬프트 폭증을 막기 위해 soft truncate.
        detail = (
            e.detail
            if len(e.detail) <= MAX_DETAIL_CHARS
            else e.detail[:MAX_DETAIL_CHARS] + "…"
        )
        lines.append(f"- 세부: {detail}")
    return "\n".join(lines)


def _build_prompt(
    entries: list[JournalEntry],
    target_date: date,
    farm_name: str | None,
    weather: str | None,
    missing: list[dict],
) -> str:
    date_str = target_date.strftime("%Y년 %m월 %d일")
    header = f"작성일: {date_str}"
    if farm_name:
        header = f"농장: {farm_name}\n{header}"
    if weather:
        header += f"\n날씨: {weather}"

    # 극단적 사례(하루 N백 건)에 대비한 soft cap — 초과분은 요약 문구로 대체.
    shown = entries[:MAX_ENTRIES_IN_PROMPT]
    overflow = len(entries) - len(shown)
    entry_blocks = "\n\n".join(
        _format_entry_block(i + 1, e) for i, e in enumerate(shown)
    )
    overflow_note = (
        f"\n\n(이 외 {overflow}건은 분량 제한으로 본 요약에서 생략됨)"
        if overflow > 0
        else ""
    )

    missing_section = ""
    if missing:
        lines = [f"- [{m['field_name']}] {m['message']}" for m in missing]
        missing_section = "\n\n누락 확인 필요:\n" + "\n".join(lines)

    return (
        f"{header}\n\n"
        f"오늘 기록된 작업 {len(entries)}건:\n\n"
        f"{entry_blocks}"
        f"{overflow_note}"
        f"{missing_section}\n\n"
        "위 기록들을 바탕으로 하루치 영농일지를 서술형으로 작성해 주세요."
    )


def _fallback_template(
    entries: list[JournalEntry],
    target_date: date,
    weather: str | None,
    missing: list[dict],
) -> str:
    """LLM 호출 실패 시 사용할 기계적 폴백 서술."""
    date_str = target_date.strftime("%Y년 %m월 %d일")
    parts = [f"{date_str} 영농일지."]
    if weather:
        parts.append(f"날씨는 {weather}으로 기록되었다.")
    parts.append(f"오늘은 총 {len(entries)}건의 작업을 수행하였다.")

    for i, e in enumerate(entries, start=1):
        frag = f"{i}) {e.field_name}에서 {e.crop} {e.work_stage} 작업을 진행하였다"
        if e.usage_pesticide_product:
            frag += f" — 농약 {e.usage_pesticide_product}"
            if e.usage_pesticide_amount:
                frag += f" {e.usage_pesticide_amount}"
            frag += " 사용"
        if e.usage_fertilizer_product:
            frag += f" — 비료 {e.usage_fertilizer_product}"
            if e.usage_fertilizer_amount:
                frag += f" {e.usage_fertilizer_amount}"
            frag += " 사용"
        if e.detail:
            frag += f". 세부: {e.detail}"
        parts.append(frag + ".")

    if missing:
        parts.append(f"확인이 필요한 누락 항목이 {len(missing)}건 있다.")

    return " ".join(parts)


async def compose_daily_journal(
    entries: list[JournalEntry],
    target_date: date,
    farm_name: str | None = None,
) -> dict:
    """LLM으로 서술형 본문 생성.

    Returns:
        {
            "narrative": str,
            "narrative_source": "llm" | "template_fallback",
            "llm_model": str | None,
            "llm_prompt_version": str,
            "missing_count": int,
        }
    """
    weathers = [e.weather for e in entries if e.weather]
    weather = weathers[0] if weathers else None
    missing = check_missing_fields(entries)

    prompt = _build_prompt(entries, target_date, farm_name, weather, missing)

    llm = get_llm_client()
    llm_model = getattr(llm, "model", None) or settings.LLM_MODEL

    # Litellm proxy 간헐적 장애 (504 timeout / model=None / rate limit)에 대비한 자동 재시도.
    # 총 3회 시도, 실패 시 2초·4초 backoff. 전부 실패하면 템플릿 폴백.
    MAX_ATTEMPTS = 3
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            narrative = await llm.generate(prompt, system=SYSTEM_PROMPT)
            narrative = (narrative or "").strip()
            if not narrative:
                raise ValueError("empty narrative")
            if attempt > 1:
                logger.info(
                    "DailyJournal LLM 성공 (재시도 %d회차, date=%s)", attempt, target_date
                )
            return {
                "narrative": narrative,
                "narrative_source": "llm",
                "llm_model": llm_model,
                "llm_prompt_version": PROMPT_VERSION,
                "missing_count": len(missing),
            }
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                backoff = 2 * attempt
                logger.warning(
                    "DailyJournal LLM 시도 %d/%d 실패 — %ds 후 재시도: %s",
                    attempt, MAX_ATTEMPTS, backoff, exc,
                )
                await asyncio.sleep(backoff)

    logger.warning(
        "DailyJournal LLM %d회 시도 모두 실패 — 템플릿 폴백 (date=%s, entries=%d): %s",
        MAX_ATTEMPTS, target_date, len(entries), last_exc,
    )
    return {
        "narrative": _fallback_template(entries, target_date, weather, missing),
        "narrative_source": "template_fallback",
        "llm_model": None,
        "llm_prompt_version": PROMPT_VERSION,
        "missing_count": len(missing),
    }
