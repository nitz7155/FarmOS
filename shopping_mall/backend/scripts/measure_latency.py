"""RAG 파이프라인 컴포넌트별 레이턴시 측정.

서버 없이 각 단계를 독립 측정해 병목 위치를 파악한다.

실행:
    uv run python scripts/measure_latency.py
    uv run python scripts/measure_latency.py --query "환불 기간이 얼마나 되나요"
"""
import argparse
import sys
import os
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

QUERY = "환불 기간이 얼마나 되나요?"
POLICY_COLLECTIONS = [
    "return_policy", "payment_policy", "delivery_policy",
    "membership_policy", "quality_policy", "service_policy",
]


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _bar(ms: int, scale: int = 20) -> str:
    filled = min(int(ms / scale), 40)
    return "#" * filled + "-" * (40 - filled)


def measure(query: str) -> None:
    print(f"\n질문: {query!r}")
    print("=" * 60)

    # ── 1. RAGService 초기화 ──────────────────────────────────────────
    t0 = time.monotonic()
    from ai.rag import RAGService, normalize_query, _split_query, _load_bm25, rerank
    init_ms = _ms(t0)
    print(f"[import]       {init_ms:>5}ms  {_bar(init_ms)}")

    t0 = time.monotonic()
    rag = RAGService()
    rag_init_ms = _ms(t0)
    print(f"[RAGService()]  {rag_init_ms:>5}ms  {_bar(rag_init_ms)}")

    # ── 2. 쿼리 전처리 ──────────────────────────────────────────────
    t0 = time.monotonic()
    sub_queries = _split_query(query)
    preprocess_ms = _ms(t0)
    print(f"[_split_query]  {preprocess_ms:>5}ms  {_bar(preprocess_ms)}  → {sub_queries}")

    # ── 3. Dense 검색 (retrieve_with_scores) ────────────────────────
    t0 = time.monotonic()
    dense_docs = []
    for sq in sub_queries:
        for doc, dist in rag.retrieve_with_scores(sq, POLICY_COLLECTIONS[0], top_k=5):
            dense_docs.append((doc, dist))
    dense_ms = _ms(t0)
    print(f"[dense]        {dense_ms:>5}ms  {_bar(dense_ms)}  → {len(dense_docs)}개 후보")

    # ── 4. BM25 로딩 (최초 1회) ─────────────────────────────────────
    t0 = time.monotonic()
    bm25_obj, bm25_meta = _load_bm25()
    bm25_load_ms = _ms(t0)
    status = f"{len(bm25_meta['ids'])}개 문서" if bm25_obj else "인덱스 없음 (seed_rag.py 필요)"
    print(f"[bm25_load]    {bm25_load_ms:>5}ms  {_bar(bm25_load_ms)}  → {status}")

    # ── 5. hybrid_retrieve (Dense + BM25 + RRF) ─────────────────────
    t0 = time.monotonic()
    seen: set[str] = set()
    candidates: list[str] = []
    for sq in sub_queries:
        for doc in rag.hybrid_retrieve(sq, POLICY_COLLECTIONS, top_k=5):
            if doc not in seen:
                seen.add(doc)
                candidates.append(doc)
    hybrid_ms = _ms(t0)
    print(f"[hybrid]       {hybrid_ms:>5}ms  {_bar(hybrid_ms)}  → {len(candidates)}개 후보")

    # ── 6. Reranker 로딩 (최초 1회) ─────────────────────────────────
    from app.core.config import settings
    if settings.reranker_model:
        from ai.rag import _load_reranker
        t0 = time.monotonic()
        reranker = _load_reranker(settings.reranker_model)
        reranker_load_ms = _ms(t0)
        print(f"[reranker_load]{reranker_load_ms:>5}ms  {_bar(reranker_load_ms)}")

        # ── 7. Rerank (predict) ──────────────────────────────────────
        if candidates and reranker:
            t0 = time.monotonic()
            final_docs = rerank(query, candidates, top_k=3)
            rerank_ms = _ms(t0)
            print(f"[rerank]       {rerank_ms:>5}ms  {_bar(rerank_ms)}  → {len(final_docs)}개 최종 ({len(candidates)}개 입력)")
        else:
            rerank_ms = 0
            final_docs = candidates[:3]
            print(f"[rerank]          -ms  (후보 없음 또는 reranker 로드 실패)")
    else:
        reranker_load_ms = 0
        rerank_ms = 0
        final_docs = candidates[:3]
        print(f"[rerank]          -ms  (RERANKER_MODEL 비어있음 — 비활성화)")

    # ── 요약 ────────────────────────────────────────────────────────
    rag_total = dense_ms + hybrid_ms + rerank_ms
    print()
    print("─" * 60)
    print(f"RAG 합계 (Dense+Hybrid+Rerank): {rag_total}ms")
    print()
    print("※ LLM 호출 레이턴시는 provider에 따라 다름:")
    print("  - Supervisor LLM:   ~500ms–3s (tool_use 1회)")
    print("  - CS Agent LLM:     ~500ms–3s (tool_use 1회)")
    print("  - Output LLM:       ~500ms–3s (합성 1회)")
    print("  → 일반 RAG 질의 총 예상: LLM 2~3회 + RAG")
    print()

    if final_docs:
        print("최종 선택 문서 (상위 1개 미리보기):")
        print(f"  {final_docs[0][:120].replace(chr(10), ' ')}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 파이프라인 레이턴시 측정")
    parser.add_argument("--query", default=QUERY, help="테스트 쿼리")
    args = parser.parse_args()
    measure(args.query)
    print("\n완료.")


if __name__ == "__main__":
    main()
