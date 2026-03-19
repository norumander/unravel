"""Unit tests for RAG embedder and ChromaDB store."""

import pytest

from app.bundle.chunker import Chunk
from app.models.schemas import SignalType
from app.rag.embedder import RAGStore, EmbeddingError


def _make_chunks(n: int, signal_type: SignalType = SignalType.events) -> list[Chunk]:
    return [
        Chunk(
            text=f"chunk content {i}",
            file_path=f"bundle/file_{i}.txt",
            signal_type=signal_type,
            chunk_index=i,
        )
        for i in range(n)
    ]


class TestRAGStoreCreate:
    def test_create_collection(self):
        store = RAGStore()
        collection_name = store.create_collection("test-session-1", _make_chunks(3))
        assert collection_name is not None
        assert store.collection_exists(collection_name)

    def test_create_collection_embeds_all_chunks(self):
        store = RAGStore()
        chunks = _make_chunks(5)
        name = store.create_collection("test-session-2", chunks)
        results = store.query(name, "chunk content", n_results=10)
        assert len(results) == 5

    def test_empty_chunks_returns_none(self):
        store = RAGStore()
        name = store.create_collection("test-session-3", [])
        assert name is None


class TestRAGStoreQuery:
    def test_query_returns_relevant_results(self):
        store = RAGStore()
        chunks = [
            Chunk(text="pod crash loop backoff OOM killed", file_path="logs/pod.log",
                  signal_type=SignalType.pod_logs, chunk_index=0),
            Chunk(text="healthy pod running normally all checks passing", file_path="logs/healthy.log",
                  signal_type=SignalType.pod_logs, chunk_index=0),
            Chunk(text="certificate expired TLS handshake failed", file_path="logs/tls.log",
                  signal_type=SignalType.pod_logs, chunk_index=0),
        ]
        name = store.create_collection("test-session-4", chunks)
        results = store.query(name, "pod crashing OOM", n_results=2)
        assert len(results) == 2
        assert "crash" in results[0].text or "OOM" in results[0].text

    def test_query_includes_metadata(self):
        store = RAGStore()
        chunks = _make_chunks(3, SignalType.pod_logs)
        name = store.create_collection("test-session-5", chunks)
        results = store.query(name, "chunk content", n_results=1)
        assert results[0].file_path.startswith("bundle/")
        assert results[0].signal_type == SignalType.pod_logs


class TestRAGStoreCleanup:
    def test_delete_collection(self):
        store = RAGStore()
        name = store.create_collection("test-session-6", _make_chunks(2))
        assert store.collection_exists(name)
        store.delete_collection(name)
        assert not store.collection_exists(name)

    def test_delete_nonexistent_collection_no_error(self):
        store = RAGStore()
        store.delete_collection("nonexistent")

class TestRAGStoreFallback:
    def test_store_reports_availability(self):
        store = RAGStore()
        assert store.is_available() is True
