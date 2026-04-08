"""ChromaDB RAG 데이터 적재 스크립트.

실행: uv run python ai/seed_rag.py
"""
import json
import os
import sys

from ai import CHROMA_DB_PATH

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CHROMA_DIR = CHROMA_DB_PATH


def load_json(filename: str) -> list:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"[경고] 파일 없음: {path} — 해당 컬렉션을 건너뜁니다.")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_embedding_function():
    try:
        from chromadb.utils import embedding_functions
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
        )
    except Exception as e:
        print(f"[경고] 임베딩 모델 로드 실패: {e}")
        print("  → sentence-transformers 설치 필요: uv add sentence-transformers")
        sys.exit(1)


def seed_faq(client, ef) -> int:
    data = load_json("faq.json")
    if not data:
        return 0

    # Delete existing collection to remove stale embeddings
    try:
        client.delete_collection(name="faq")
    except Exception:
        pass  # Collection doesn't exist yet, which is fine

    col = client.get_or_create_collection(name="faq", embedding_function=ef)

    ids, documents, metadatas = [], [], []
    for item in data:
        chunk_text = f"Q: {item['question']}\nA: {item['answer']}"
        ids.append(item["id"])
        documents.append(chunk_text)
        metadatas.append({
            "type": "faq",
            "intent": item["intent"],
            "faq_id": item["id"],
        })

    col.upsert(documents=documents, metadatas=metadatas, ids=ids)
    return col.count()


def seed_storage_guide(client, ef) -> int:
    data = load_json("storage_guide.json")
    if not data:
        return 0

    # Delete existing collection to remove stale embeddings
    try:
        client.delete_collection(name="storage_guide")
    except Exception:
        pass  # Collection doesn't exist yet, which is fine

    col = client.get_or_create_collection(name="storage_guide", embedding_function=ef)

    ids, documents, metadatas = [], [], []
    for item in data:
        ids.append(item["id"])
        documents.append(item["guide"])
        metadatas.append({
            "type": "storage",
            "product_name": item["product"],
            "category": item["category"],
        })

    col.upsert(documents=documents, metadatas=metadatas, ids=ids)
    return col.count()


def seed_season_info(client, ef) -> int:
    data = load_json("season_info.json")
    if not data:
        return 0

    # Delete existing collection to remove stale embeddings
    try:
        client.delete_collection(name="season_info")
    except Exception:
        pass  # Collection doesn't exist yet, which is fine

    col = client.get_or_create_collection(name="season_info", embedding_function=ef)

    ids, documents, metadatas = [], [], []
    for item in data:
        products_text = ", ".join(item["products"]) if item["products"] else "없음"
        doc_text = f"{item['season']} 제철 상품: {products_text}\n{item['description']}"
        ids.append(item["id"])
        documents.append(doc_text)
        metadatas.append({
            "type": "season",
            "season": item["season"],
        })

    col.upsert(documents=documents, metadatas=metadatas, ids=ids)
    return col.count()


def main():
    try:
        import chromadb
    except ImportError:
        print("[오류] chromadb 설치 필요: uv add chromadb")
        sys.exit(1)

    print("ChromaDB 초기화 중...")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    ef = get_embedding_function()

    print("faq 적재 중...")
    faq_count = seed_faq(client, ef)

    print("storage_guide 적재 중...")
    storage_count = seed_storage_guide(client, ef)

    print("season_info 적재 중...")
    season_count = seed_season_info(client, ef)

    print(f"\n완료: faq={faq_count}개, storage_guide={storage_count}개, season_info={season_count}개")
    print(f"저장 경로: {os.path.abspath(CHROMA_DIR)}")


if __name__ == "__main__":
    main()
