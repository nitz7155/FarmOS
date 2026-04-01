"""ChromaDB 벡터 데이터베이스 연결 및 컬렉션 관리.

ChromaDB는 텍스트를 벡터(숫자 배열)로 변환하여 저장하고,
의미적으로 유사한 텍스트를 검색할 수 있는 벡터 데이터베이스입니다.

사용 예시:
    from app.core.vectordb import get_collection

    # 컬렉션 가져오기 (없으면 자동 생성)
    collection = get_collection("diagnosis")

    # 데이터 추가
    collection.add(
        documents=["사과 탄저병 증상: 과실에 갈색 반점"],
        metadatas=[{"crop": "사과", "pest": "탄저병"}],
        ids=["diag-001"],
    )

    # 유사 검색 (의미적으로 비슷한 문서를 찾아줌)
    results = collection.query(
        query_texts=["사과에 갈색 점이 생겼어요"],
        n_results=3,
    )
"""

import chromadb
from chromadb.config import Settings

from app.core.config import settings

# ChromaDB 클라이언트 (싱글턴)
_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    """ChromaDB 클라이언트를 반환한다 (최초 호출 시 생성)."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_DB_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection(name: str) -> chromadb.Collection:
    """컬렉션을 가져온다 (없으면 자동 생성).

    컬렉션 = 관련 데이터를 묶는 단위 (RDB의 테이블과 유사)

    Args:
        name: 컬렉션 이름 (예: "diagnosis", "journal", "documents")
    """
    client = get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},  # 코사인 유사도 사용
    )


def reset_client():
    """테스트용 — 클라이언트 초기화."""
    global _client
    _client = None
