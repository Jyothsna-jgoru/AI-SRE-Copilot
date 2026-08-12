from __future__ import annotations

from functools import lru_cache

from backend.config import get_settings


class ChromaKnowledgeStore:
    def __init__(self) -> None:
        import chromadb
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        self.client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        self.collection = self.client.get_or_create_collection(
            settings.chroma_collection,
            metadata={"description": "AI SRE operational evidence"},
        )
        self.embedding_model = SentenceTransformer(settings.embedding_model)

    def index(self, documents: list[dict]) -> int:
        if not documents:
            return 0
        texts = [document["content"] for document in documents]
        embeddings = self.embedding_model.encode(texts, normalize_embeddings=True).tolist()
        metadatas = [
            {
                "document_type": document["document_type"],
                "service_name": document["service_name"],
                "scenario": document["scenario"],
                "title": document["title"],
            }
            for document in documents
        ]
        self.collection.upsert(
            ids=[document["id"] for document in documents],
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return len(documents)

    def query(self, text: str, service_name: str | None = None, limit: int = 5) -> list[dict]:
        embedding = self.embedding_model.encode([text], normalize_embeddings=True).tolist()
        where = {"service_name": service_name} if service_name else None
        result = self.collection.query(
            query_embeddings=embedding,
            n_results=limit,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        output: list[dict] = []
        for index, document_id in enumerate(result.get("ids", [[]])[0]):
            output.append(
                {
                    "id": document_id,
                    "content": result["documents"][0][index],
                    "metadata": result["metadatas"][0][index],
                    "distance": result["distances"][0][index],
                }
            )
        return output


@lru_cache(maxsize=1)
def get_knowledge_store() -> ChromaKnowledgeStore:
    return ChromaKnowledgeStore()

