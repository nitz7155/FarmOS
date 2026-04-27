"""shop_reviews 더미 리뷰 1,000건 시드.

`bootstrap/insert_data.py`(Phase 2) 가 `seed_shoppingmall_reviews()` 를 호출한다.

멱등성 보장 (plan §4):
- 기존 코드의 `DELETE FROM shop_reviews` 라인은 제거되었다(데이터 손실 위험).
- INSERT 는 `id` 를 명시하여 `ON CONFLICT (id) DO NOTHING` 으로 동작한다.
  → 같은 id 가 이미 있으면 스킵, 없으면 추가 (가산형).
- 추가 안전장치: 시작 시점에 `shop_reviews` row 수가 1000건 이상이면 전체 스킵.

`random.seed(42)` 로 시퀀스가 고정되므로 같은 id 의 컨텐츠가 매번 동일하다.
"""

# ruff: noqa: E402
# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
SHOP_BACKEND_DIR = ROOT / "shopping_mall" / "backend"
if str(SHOP_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(SHOP_BACKEND_DIR))

from app.database import SessionLocal

REVIEW_TARGET_COUNT = 1000
REVIEW_RANDOM_SEED = 42

POSITIVE_TEMPLATES = [
    "정말 맛있어요! {product} 품질이 최고입니다.",
    "{product} 너무 신선하고 좋아요. 재구매 의사 100%!",
    "포장도 꼼꼼하고 {product} 상태 완벽했어요.",
    "기대 이상이에요. {product}이/가 정말 달고 맛있어요!",
    "배송도 빠르고 {product} 품질도 좋아서 만족합니다.",
    "선물용으로 구매했는데 받는 분이 너무 좋아하셨어요.",
    "매번 여기서 주문하는데 항상 품질이 일정해요. 믿고 삽니다.",
    "가격 대비 품질이 너무 좋아요. {product} 추천합니다!",
    "아이들이 {product} 너무 좋아해요. 또 시킬게요.",
    "산지 직송이라 신선도가 다릅니다. {product} 최고!",
    "당도가 높아서 설탕 없이도 달아요. 건강한 간식!",
    "어머니가 {product} 드시고 너무 맛있다고 하셨어요.",
    "이 가격에 이 품질이라니, 완전 가성비 갑!",
    "{product} 크기도 크고 상태도 좋아요. 만족스럽습니다.",
    "주문하고 다음 날 바로 왔어요. 신선도 최상!",
    "진짜 맛있어서 주변에 소문내고 다녀요ㅋㅋ",
    "사진이랑 똑같이 왔어요. 상품 상태 아주 좋습니다.",
    "처음 주문했는데 감동이에요. 단골 될게요!",
    "명절 선물로 보냈는데 진짜 고급스러워요.",
    "{product} 진짜 실망 없어요. 벌써 3번째 주문!",
    "냉장 배송이라 신선하게 도착했어요. 감사합니다.",
    "유기농이라 안심하고 먹을 수 있어요.",
    "식구들이 다 좋아해서 대량으로 시켰어요. 만족!",
    "요리해서 먹었는데 {product} 맛이 살아있어요!",
    "국내산이라 믿음이 가요. 앞으로도 여기서 구매할게요.",
    "이번에도 역시 품질 좋습니다. 믿고 구매해요.",
    "파트너에게 선물했는데 너무 좋아했어요!",
    "산지에서 바로 보내주셔서 그런지 향이 진해요.",
    "{product} 진짜 싱싱해요. 마트보다 훨씬 좋습니다.",
    "가격도 착하고 맛도 좋고. 완벽해요!",
    "당도 14Brix 이상이에요! {product} 꿀맛입니다.",
    "{product} 아삭하고 달콤해요. 온 가족이 좋아합니다.",
    "택배 아저씨도 조심히 다뤄주셨어요. {product} 멀쩡하게 도착!",
    "우리 아기 이유식에 {product} 넣었더니 잘 먹어요.",
    "친구한테 추천받고 샀는데 진짜 맛있네요!",
    "할머니댁에 보내드렸더니 너무 좋아하세요. {product} 최고!",
    "{product} 색깔도 예쁘고 당도도 높아요. 대만족!",
    "마트에서 사먹다가 여기로 바꿨는데 퀄리티 차이 큽니다.",
    "단체 주문했는데 하나하나 상태가 좋아요. {product} 강추!",
    "육즙이 살아있어요. {product} 요리하니까 맛이 다르네요.",
]

NEUTRAL_TEMPLATES = [
    "{product} 보통이에요. 가격 대비 무난합니다.",
    "기대했던 것보다 평범해요. 그래도 나쁘지는 않아요.",
    "{product} 괜찮긴 한데 특별히 맛있다는 느낌은 없어요.",
    "그냥 무난한 {product}이에요. 다시 살지는 모르겠어요.",
    "가격이 좀 있는데 그만한 가치인지는 잘 모르겠어요.",
    "포장은 잘 되어 있는데 맛은 기대만큼은 아니에요.",
    "배송은 빨랐는데 {product} 크기가 좀 작아요.",
    "그럭저럭 먹을 만해요. 마트 것과 비슷한 수준.",
    "첫 구매라 잘 모르겠는데 보통인 것 같아요.",
    "{product} 상태는 괜찮은데 양이 좀 적어요.",
    "나쁘지 않아요. 근데 재구매는 고민 중이에요.",
    "사진보다 좀 작아 보여요. 맛은 괜찮아요.",
    "배송이 좀 늦었지만 상품은 무난해요.",
    "기대가 커서 그런지 약간 아쉬워요. 평범한 {product}.",
    "가성비는 그저 그래요. 할인할 때 사면 좋을 듯.",
    "다른 데서 사던 것과 크게 차이가 없어요.",
    "선물로 보내기엔 좀 애매한 크기예요.",
    "맛은 있는데 가격이 좀 비싼 감이 있어요.",
    "무난하게 먹기 좋아요. 특별하진 않지만요.",
    "{product} 호불호가 갈릴 수 있을 것 같아요.",
    "신선하긴 한데 기대했던 당도는 아니에요.",
    "포장은 깔끔한데 한두 개 상태가 좀 아쉬워요.",
    "급하게 필요해서 샀는데 보통 수준이에요.",
    "맛은 괜찮은데 양이 좀 부족한 느낌이에요.",
    "사진이랑 좀 다른 느낌인데, 나쁘진 않아요.",
    "어디서 사나 비슷비슷한 {product}인 것 같아요.",
    "보통이요. 특별한 건 없어요.",
    "그냥 평범한 {product}이에요. 가격은 적당해요.",
    "괜찮아요. 크게 감동은 없지만 불만도 없어요.",
    "두 번째 구매인데 처음이랑 맛이 좀 다른 느낌?",
]

NEGATIVE_TEMPLATES = [
    "{product} 포장이 엉망이에요. 배송 중 상했어요.",
    "기대 이하입니다. {product} 신선도가 많이 떨어져요.",
    "사진이랑 너무 다르네요. {product} 크기가 너무 작아요.",
    "배송이 3일이나 걸렸어요. 도착했을 때 이미 물러져 있었어요.",
    "{product}에서 곰팡이가 발견됐어요. 환불 요청합니다.",
    "가격 대비 너무 별로예요. 마트가 더 나을 뻔했어요.",
    "포장이 부실해서 배송 중에 다 으깨졌어요.",
    "맛도 없고 신선하지도 않고... 실망이에요.",
    "멍 든 {product}이/가 절반이에요. 선별을 제대로 안 한 것 같아요.",
    "두 번 다시 안 삽니다. 품질 관리 좀 해주세요.",
    "배송 중 온도 관리가 안 되는 건지 녹아있었어요.",
    "표시된 중량보다 훨씬 적게 왔어요. 양심이 있나요?",
    "냄새가 이상해요. 먹기 찝찝합니다.",
    "상태가 너무 안 좋아서 반이나 버렸어요.",
    "이 가격에 이 품질은 좀... 다른 데로 갈래요.",
    "사진 속 {product}이랑 실물이 너무 달라요.",
    "포장 박스가 찌그러져서 왔어요. 내용물도 손상.",
    "완전 실망했어요. 이건 팔면 안 되는 수준이에요.",
    "CS 문의했는데 답변도 느리고 환불도 안 해줘요.",
    "벌레가 나왔어요... 관리가 너무 안 되는 것 같아요.",
    "{product} 당도가 1도 안 되는 느낌이에요. 물맛.",
    "껍질이 다 까져있고 멍투성이에요. {product} 상태 최악.",
    "냉동 상태로 와야 하는데 다 녹아서 물이 줄줄.",
    "크기도 작고 맛도 없어요. 사진은 뭘 찍은 건지...",
    "3만원 주고 이걸 받을 줄은 몰랐어요. 환불해주세요.",
]

PRODUCT_NAMES = [
    "경북 부사 사과 5kg",
    "충남 신고배 7.5kg",
    "청송 꿀사과 3kg",
    "나주배 선물세트 5kg",
    "홍로사과 2kg",
    "제주 감귤 5kg",
    "제주 한라봉 3kg",
    "카라카라 오렌지 2kg",
    "천혜향 2kg",
    "레드향 3kg",
    "유기농 상추 300g",
    "깻잎 100매",
    "시금치 500g",
    "배추 1포기",
    "청경채 200g",
    "감자 3kg",
    "고구마 3kg",
    "당근 1kg",
    "양파 3kg",
    "무 1개",
    "한우 등심 1++ 300g",
    "한우 갈비살 500g",
    "한우 채끝 200g",
    "한우 불고기용 300g",
    "한우 사골 2kg",
    "제주 흑돼지 삼겹살 500g",
    "목살 구이용 500g",
    "돼지갈비 양념 1kg",
    "노르웨이 생연어 300g",
    "제주 광어회 500g",
    "고등어 2마리",
    "참치회 400g",
    "갈치 2마리",
    "통영 생굴 1kg",
    "킹크랩 1마리 (1.5kg)",
    "새우 (대) 1kg",
    "전복 10마리",
    "오징어 3마리",
    "유기농 블루베리 500g",
    "친환경 방울토마토 1kg",
    "유기농 브로콜리 2개",
    "흙당근 2kg",
]
PRODUCT_IDS = list(range(1, 43))
USER_IDS = list(range(1, 6))


def _log(message: str) -> None:
    print(f"[shoppingmall_review_seed] {message}")


def generate_review(review_id: int, sentiment: str, product_id: int) -> dict:
    product_name = (
        PRODUCT_NAMES[product_id - 1] if product_id <= len(PRODUCT_NAMES) else "상품"
    )

    if sentiment == "positive":
        template = random.choice(POSITIVE_TEMPLATES)
        rating = random.choice([4, 4, 5, 5, 5])
    elif sentiment == "neutral":
        template = random.choice(NEUTRAL_TEMPLATES)
        rating = 3
    else:
        template = random.choice(NEGATIVE_TEMPLATES)
        rating = random.choice([1, 1, 2, 2])

    content = template.format(product=product_name)
    days_ago = random.randint(0, 90)
    created_at = datetime.now() - timedelta(days=days_ago)

    return {
        "id": review_id,
        "product_id": product_id,
        "user_id": random.choice(USER_IDS),
        "rating": float(rating),
        "content": content,
        "created_at": created_at,
    }


def generate_all_reviews(count: int = REVIEW_TARGET_COUNT) -> list[dict]:
    positive_count = int(count * 0.50)
    negative_count = int(count * 0.25)
    neutral_count = count - positive_count - negative_count

    reviews = []
    review_id = 1

    sentiments = (
        ["positive"] * positive_count
        + ["negative"] * negative_count
        + ["neutral"] * neutral_count
    )
    random.shuffle(sentiments)

    for sentiment in sentiments:
        product_id = random.choice(PRODUCT_IDS)
        reviews.append(generate_review(review_id, sentiment, product_id))
        review_id += 1

    return reviews


def seed_shoppingmall_reviews(count: int = REVIEW_TARGET_COUNT) -> int:
    """`shop_reviews` 에 더미 리뷰를 멱등 INSERT 한다.

    멱등성:
    - `id` 를 명시하고 `ON CONFLICT (id) DO NOTHING` 사용 → 기존 row 보존, 누락분만 추가.
    - 시작 시점 row 수가 `count` 이상이면 전체 스킵.

    Returns:
        실제로 추가된 row 수.
    """
    random.seed(REVIEW_RANDOM_SEED)
    reviews = generate_all_reviews(count)

    db = SessionLocal()
    try:
        existing_count = int(
            db.execute(text("SELECT COUNT(*) FROM shop_reviews")).scalar() or 0
        )
        if existing_count >= count:
            _log(
                f"shop_reviews 에 이미 {existing_count}건이 있어 시드를 스킵합니다 (목표 {count})."
            )
            return 0

        _log(
            f"shop_reviews 멱등 INSERT 시작 (현재 {existing_count}건 -> 목표 {count}건)"
        )

        batch_size = 500
        total = len(reviews)
        attempted = 0

        if total == 0:
            # generate_all_reviews 가 0건을 만들면 적재할 게 없다 — 무의미한 SQL/commit 을
            # 피하고 즉시 종료. ZeroDivisionError 진행률 계산도 자연스럽게 회피된다.
            _log("생성된 리뷰가 0건 — INSERT 를 건너뜁니다.")
            return 0

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            values = [
                {
                    "id": review["id"],
                    "product_id": review["product_id"],
                    "user_id": review["user_id"],
                    "rating": review["rating"],
                    "content": review["content"],
                    "created_at": review["created_at"],
                }
                for review in batch
            ]
            db.execute(
                text(
                    """
                    INSERT INTO shop_reviews
                        (id, product_id, user_id, rating, content, created_at)
                    VALUES
                        (:id, :product_id, :user_id, :rating, :content, :created_at)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                values,
            )
            attempted += len(batch)
            # 위 early return 이 total==0 을 막아주지만, 진행률 계산은 belt-and-suspenders
            # 로 방어적 형태를 유지 — 향후 누가 early return 을 옮기더라도 깨지지 않도록.
            percent = attempted * 100 // total if total else 100
            _log(f"진행: {attempted}/{total}건 ({percent}%)")

        db.commit()

        # explicit id 로 INSERT 했으므로 `shop_reviews_id_seq` 가 max(id) 까지 따라잡지
        # 못한 상태 — 이후 정상 INSERT (id 자동 생성) 가 sequence 1부터 시도하다 PK conflict
        # 가 발생한다. setval 로 sequence 를 max(id) 로 동기화한다.
        # `setval(seq, x, true)` → 다음 nextval() 은 x+1 을 반환. COALESCE 는 빈 테이블 가드.
        db.execute(
            text(
                """
                SELECT setval(
                    pg_get_serial_sequence('shop_reviews', 'id'),
                    COALESCE((SELECT MAX(id) FROM shop_reviews), 0),
                    true
                )
                """
            )
        )
        db.commit()

        final_count = int(
            db.execute(text("SELECT COUNT(*) FROM shop_reviews")).scalar() or 0
        )
        added = max(0, final_count - existing_count)
        _log(f"shop_reviews 시드 완료: {final_count}건 (이번 추가 {added}건)")
        return added
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
