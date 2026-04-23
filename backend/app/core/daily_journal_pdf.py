"""일일 통합 영농일지 PDF — 기존 영농일지 양식 1매로 하루 작업 전체를 통합 출력.

설계:
- 기존 `JournalPDF`(헤더/푸터)와 `_draw_badge`, `_draw_chem_section`을 재사용.
- 1매 = 1 카드. 6건이든 10건이든 한 카드에 통합.
  - 헤더: "통합" 뱃지 + 작목/필지/단계 목록 + 날씨
  - 농약/비료 구입/사용 표: 모든 entry의 행을 한 표로
  - 세부작업내용: LLM이 만든 서술형 narrative
- 공개 함수:
  - `generate_daily_journal_pdf(dj, farm_name)` — 1매
  - `generate_period_pdf(djs, farm_name, date_from, date_to)` — N매(여러 날짜)
"""

from __future__ import annotations

from datetime import date

from app.core.journal_pdf import (
    JournalPDF,
    PRIMARY_LIGHT,
    GRAY_50,
    GRAY_400,
    BLACK,
    WHITE,
    BORDER_COLOR,
    PAGE_W,
    MARGIN,
    CONTENT_W,
    MAX_Y,
    _draw_badge,
)
from app.models.daily_journal import DailyJournal


# "통합" 뱃지 스타일 — 기존 작업단계 색상들과 시각적으로 구분되게 보라 톤.
UNIFIED_BADGE_STYLE = {"fg": (88, 28, 135), "bg": (243, 232, 255)}


# ──────────────────────────────────────────────
# 내부 렌더 헬퍼
# ──────────────────────────────────────────────


def _draw_unified_card_header(pdf: JournalPDF, dj: DailyJournal) -> float:
    """통합 카드의 상단 헤더 — '통합' 뱃지 + 작목 목록 + 날씨. 사용한 y 높이 반환."""
    entries = dj.entry_snapshot or []
    crops = sorted({str(e.get("crop")) for e in entries if e.get("crop")})
    weathers = [str(e.get("weather")) for e in entries if e.get("weather")]
    weather = weathers[0] if weathers else None

    x = MARGIN
    y = pdf.get_y()

    # 회색 배경
    pdf.set_fill_color(*GRAY_50)
    pdf.rect(x + 0.2, y + 0.2, CONTENT_W - 0.4, 9.8, style="F")

    # "통합" 뱃지
    badge_w = _draw_badge(pdf, "통합", x + 3, y + 2.2, UNIFIED_BADGE_STYLE)

    # 작목 (bold)
    cx = x + 3 + badge_w + 4
    pdf.set_xy(cx, y)
    pdf.set_font("malgun", "B", 9)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 10, ", ".join(crops) if crops else "-")

    # 날씨 (오른쪽)
    if weather:
        pdf.set_font("malgun", "", 8)
        pdf.set_text_color(*BLACK)
        w = pdf.get_string_width(weather)
        pdf.set_xy(x + CONTENT_W - w - 4, y)
        pdf.cell(w, 10, weather)

    pdf.set_y(y + 10)
    return 10


def _collect_chem_rows(
    entries: list[dict], usage: bool, kind: str
) -> list[tuple[str, str, str, str]]:
    """모든 entry에서 농약/비료 사용·구입 행을 수집.

    Returns:
        [(label, field_name, product, amount), ...]
        통합 카드에선 "어느 필지에 친 약/비료인지"가 중요하므로 field_name 포함.
    """
    prefix = "usage_" if usage else "purchase_"
    product_key = f"{prefix}{kind}_product"
    amount_key = f"{prefix}{kind}_amount"
    label = "농약" if kind == "pesticide" else "비료"
    rows: list[tuple[str, str, str, str]] = []
    for e in entries:
        product = e.get(product_key)
        if product:
            rows.append(
                (
                    label,
                    str(e.get("field_name") or "-"),
                    str(product),
                    str(e.get(amount_key) or ""),
                )
            )
    return rows


def _draw_unified_chem_section(
    pdf: JournalPDF,
    title: str,
    rows: list[tuple[str, str, str, str]],
    x: float,
    y: float,
) -> float:
    """통합 카드 전용 농약/비료 표.

    기존 `_draw_chem_section`(3컬럼: 구분/제품명/수량)과 동일한 스타일이지만
    "필지" 컬럼이 추가된 4컬럼 버전.
    Returns: 사용한 y 높이.
    """
    if not rows:
        return 0

    # 컬럼 너비 합 = 180mm (CONTENT_W)
    col_w = [20, 45, 70, 45]  # 구분 / 필지 / 제품명 / 수량
    headers = ["구분", "필지", "제품명", "수량/사용량"]
    row_h = 7
    total_w = sum(col_w)

    # 섹션 제목 바 (primary-light)
    pdf.set_xy(x, y)
    pdf.set_font("malgun", "B", 7.5)
    pdf.set_fill_color(*PRIMARY_LIGHT)
    pdf.set_text_color(*BLACK)
    pdf.set_draw_color(*BORDER_COLOR)
    pdf.cell(total_w, row_h, f"  {title}", fill=True, border=1)
    cy = y + row_h

    # 컬럼 헤더
    pdf.set_xy(x, cy)
    pdf.set_font("malgun", "B", 7)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_text_color(*BLACK)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], row_h, h, border=1, fill=True, align="C")
    cy += row_h

    # 데이터 행
    for label, field, product, amount in rows:
        pdf.set_xy(x, cy)
        pdf.set_text_color(*BLACK)
        pdf.set_draw_color(*BORDER_COLOR)
        pdf.set_fill_color(*WHITE)

        pdf.set_font("malgun", "B", 7.5)
        pdf.cell(col_w[0], row_h, f" {label}", border=1, fill=True)
        pdf.set_font("malgun", "", 7.5)
        pdf.cell(col_w[1], row_h, f" {field}", border=1, fill=True)
        pdf.cell(col_w[2], row_h, f" {product}", border=1, fill=True)
        pdf.cell(col_w[3], row_h, f" {amount or '-'}", border=1, fill=True)
        cy += row_h

    return cy - y


def _render_dj_on_current_page(pdf: JournalPDF, dj: DailyJournal):
    """현재 페이지에 1개 DailyJournal의 통합 카드를 그린다.

    호출자가 add_page() 한 후 호출. 빈 entry이면 안내 문구만.
    """
    entries = dj.entry_snapshot or []

    # 날짜 라벨 (기존 generate_journal_pdf와 동일 스타일)
    date_label = dj.work_date.strftime("%Y년 %m월 %d일")
    pdf.set_font("malgun", "B", 10)
    pdf.set_text_color(*BLACK)
    pdf.cell(0, 8, date_label, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BORDER_COLOR)
    pdf.set_line_width(0.3)
    pdf.line(MARGIN, pdf.get_y(), PAGE_W - MARGIN, pdf.get_y())
    pdf.ln(3)

    if not entries:
        pdf.set_font("malgun", "", 9)
        pdf.set_text_color(*GRAY_400)
        pdf.cell(0, 8, "기록된 작업이 없습니다.", align="C")
        return

    # 통합 카드 시작 — 외곽선을 그릴지 결정하려면 시작 페이지 번호도 기록.
    card_start_y = pdf.get_y()
    card_start_page = pdf.page_no()

    # 헤더 (작목/필지/단계/날씨/뱃지)
    _draw_unified_card_header(pdf, dj)
    y = pdf.get_y()

    # 농약/비료 구입 통합 표 (필지 컬럼 포함)
    purchase_rows = (
        _collect_chem_rows(entries, usage=False, kind="pesticide")
        + _collect_chem_rows(entries, usage=False, kind="fertilizer")
    )
    if purchase_rows:
        h = _draw_unified_chem_section(pdf, "농약/비료 구입", purchase_rows, MARGIN, y)
        y += h

    # 농약/비료 사용 통합 표 (필지 컬럼 포함)
    usage_rows = (
        _collect_chem_rows(entries, usage=True, kind="pesticide")
        + _collect_chem_rows(entries, usage=True, kind="fertilizer")
    )
    if usage_rows:
        h = _draw_unified_chem_section(pdf, "농약/비료 사용", usage_rows, MARGIN, y)
        y += h

    # 세부작업내용 = LLM narrative (없으면 entry detail 합치기)
    narrative = (dj.narrative or "").strip()
    if not narrative:
        details = [str(e.get("detail")) for e in entries if e.get("detail")]
        narrative = " / ".join(details) if details else " "

    pdf.set_xy(MARGIN + 3, y + 2)
    pdf.set_font("malgun", "", 8.5)
    pdf.set_text_color(*BLACK)
    pdf.multi_cell(CONTENT_W - 6, 5, narrative, max_line_height=5)
    y = pdf.get_y() + 2

    # 카드 외곽선 — 카드가 1페이지 안에 다 들어간 경우에만 그림.
    # 멀티페이지로 넘어간 경우 rect()는 현재 페이지에 그려져 좌표가 어긋나므로 생략.
    if pdf.page_no() == card_start_page and y < MAX_Y:
        pdf.set_draw_color(*BORDER_COLOR)
        pdf.set_line_width(0.4)
        pdf.rect(
            MARGIN,
            card_start_y,
            CONTENT_W,
            y - card_start_y + 1,
            round_corners=True,
            style="D",
            corner_radius=2,
        )


def _to_bytes(out) -> bytes:
    if isinstance(out, bytearray):
        return bytes(out)
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)


# ──────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────


def generate_daily_journal_pdf(dj: DailyJournal, farm_name: str = "") -> bytes:
    """단일 DailyJournal → PDF 1매."""
    pdf = JournalPDF(
        farm_name=farm_name or "-",
        date_from=dj.work_date,
        date_to=dj.work_date,
    )
    # 긴 표·narrative가 페이지 밖으로 잘리지 않도록 auto page break 활성화.
    # (JournalPDF.__init__ 기본값 False → cell/multi_cell 호출 중에만 자동 넘김).
    pdf.set_auto_page_break(auto=True, margin=MARGIN)
    pdf.add_page()
    _render_dj_on_current_page(pdf, dj)
    return _to_bytes(pdf.output())


def generate_period_pdf(
    djs: list[DailyJournal],
    farm_name: str,
    date_from: date,
    date_to: date,
) -> bytes:
    """여러 DailyJournal → PDF 묶음 (각 dj가 1매씩 들어감, 작업일 오름차순)."""
    pdf = JournalPDF(
        farm_name=farm_name or "-",
        date_from=date_from,
        date_to=date_to,
    )
    # 긴 표·narrative가 페이지 밖으로 잘리지 않도록 auto page break 활성화.
    pdf.set_auto_page_break(auto=True, margin=MARGIN)

    if not djs:
        # 빈 경우: 안내만 출력
        pdf.add_page()
        pdf.set_font("malgun", "", 10)
        pdf.set_text_color(*GRAY_400)
        pdf.ln(30)
        pdf.cell(
            0, 10,
            "해당 기간에 통합 영농일지가 없습니다.",
            align="C",
        )
        return _to_bytes(pdf.output())

    # 작업일 오름차순으로 페이지 추가
    sorted_djs = sorted(djs, key=lambda d: d.work_date)
    for dj in sorted_djs:
        pdf.add_page()
        _render_dj_on_current_page(pdf, dj)

    return _to_bytes(pdf.output())
