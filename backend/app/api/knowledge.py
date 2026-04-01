"""병해충 진단 지식 베이스 API — ChromaDB 벡터 검색.

ChromaDB를 활용하여 병해충 진단 사례를 저장하고,
자연어로 유사한 사례를 검색할 수 있는 API입니다.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.vectordb import get_collection

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

COLLECTION_NAME = "diagnosis_knowledge"


# ── 스키마 ──────────────────────────────────────


class KnowledgeEntry(BaseModel):
    """지식 베이스에 추가할 항목."""
    id: str = Field(description="고유 ID (예: 'diag-001')")
    content: str = Field(description="진단 내용 텍스트")
    crop: str = Field(default="", description="작물명 (예: '사과')")
    pest: str = Field(default="", description="병해충명 (예: '탄저병')")
    severity: str = Field(default="", description="심각도 (예: '경증')")


class SearchQuery(BaseModel):
    """유사 검색 쿼리."""
    query: str = Field(description="검색할 자연어 문장")
    n_results: int = Field(default=5, ge=1, le=20, description="반환할 결과 수")
    crop_filter: str | None = Field(default=None, description="작물명 필터 (선택)")


# ── API 엔드포인트 ──────────────────────────────


@router.post("/add", dependencies=[Depends(get_current_user)])
async def add_knowledge(entry: KnowledgeEntry) -> dict:
    """진단 지식을 벡터 DB에 추가한다."""
    collection = get_collection(COLLECTION_NAME)
    collection.upsert(
        ids=[entry.id],
        documents=[entry.content],
        metadatas=[{
            "crop": entry.crop,
            "pest": entry.pest,
            "severity": entry.severity,
        }],
    )
    return {"status": "ok", "id": entry.id}


@router.post("/search", dependencies=[Depends(get_current_user)])
async def search_knowledge(query: SearchQuery) -> dict:
    """자연어로 유사한 진단 사례를 검색한다."""
    collection = get_collection(COLLECTION_NAME)

    # 컬렉션이 비어있으면 빈 결과 반환
    if collection.count() == 0:
        return {"results": [], "total_in_db": 0}

    # 작물 필터 설정
    where_filter = {"crop": query.crop_filter} if query.crop_filter else None

    results = collection.query(
        query_texts=[query.query],
        n_results=min(query.n_results, collection.count()),
        where=where_filter,
    )

    # 결과 정리
    items = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            items.append({
                "id": doc_id,
                "content": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
            })

    return {"results": items, "total_in_db": collection.count()}


@router.get("/stats", dependencies=[Depends(get_current_user)])
async def knowledge_stats() -> dict:
    """지식 베이스 통계를 반환한다."""
    collection = get_collection(COLLECTION_NAME)
    return {
        "collection": COLLECTION_NAME,
        "total_entries": collection.count(),
    }
