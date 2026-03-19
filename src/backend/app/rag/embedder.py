"""RAG store — embeds chunks and manages ChromaDB collections for semantic search."""

import logging
from dataclasses import dataclass

import chromadb
from sentence_transformers import SentenceTransformer

from app.bundle.chunker import Chunk
from app.models.schemas import SignalType

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingError(Exception):
    """Raised when embedding or vector store operations fail."""


@dataclass
class SearchResult:
    text: str
    file_path: str
    signal_type: SignalType
    chunk_index: int
    score: float


class RAGStore:
    def __init__(self) -> None:
        self._client = chromadb.Client()
        self._model: SentenceTransformer | None = None
        self._available = True
        try:
            self._model = SentenceTransformer(_MODEL_NAME)
        except Exception:
            logger.warning("Failed to load embedding model '%s'. RAG disabled.", _MODEL_NAME, exc_info=True)
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def create_collection(self, session_id: str, chunks: list[Chunk]) -> str | None:
        if not chunks:
            return None
        if not self._available or self._model is None:
            return None

        collection_name = f"session-{session_id}"
        collection = self._client.create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})

        texts = [c.text for c in chunks]
        embeddings = self._model.encode(texts, show_progress_bar=False).tolist()
        ids = [f"{c.file_path}::{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "file_path": c.file_path,
                "signal_type": c.signal_type.value,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]

        collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        logger.info("Created collection '%s' with %d chunks", collection_name, len(chunks))
        return collection_name

    def query(self, collection_name: str, query_text: str, n_results: int = 10) -> list[SearchResult]:
        if not self._available or self._model is None:
            return []
        collection = self._client.get_collection(collection_name)
        query_embedding = self._model.encode([query_text], show_progress_bar=False).tolist()
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(n_results, collection.count()),
        )

        search_results = []
        if results["documents"] and results["metadatas"] and results["distances"]:
            for doc, meta, dist in zip(
                results["documents"][0], results["metadatas"][0], results["distances"][0]
            ):
                search_results.append(
                    SearchResult(
                        text=doc,
                        file_path=meta["file_path"],
                        signal_type=SignalType(meta["signal_type"]),
                        chunk_index=meta["chunk_index"],
                        score=1.0 - dist,
                    )
                )
        return search_results

    def collection_exists(self, collection_name: str) -> bool:
        try:
            self._client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def delete_collection(self, collection_name: str) -> None:
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass
