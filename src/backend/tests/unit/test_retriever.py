"""Unit tests for diagnostic query retriever."""

from app.bundle.chunker import Chunk
from app.models.schemas import SignalType
from app.rag.embedder import RAGStore, SearchResult
from app.rag.retriever import retrieve_analysis_context, retrieve_for_query


class TestRetrieveAnalysisContext:
    def test_returns_chunks_grouped_by_signal_type(self):
        store = RAGStore()
        chunks = [
            Chunk(text="pod crash loop", file_path="logs/pod.log",
                  signal_type=SignalType.pod_logs, chunk_index=0),
            Chunk(text="event warning backoff", file_path="events.json",
                  signal_type=SignalType.events, chunk_index=0),
            Chunk(text="node not ready", file_path="nodes/node1.json",
                  signal_type=SignalType.node_status, chunk_index=0),
        ]
        name = store.create_collection("test-ret-1", chunks)
        context = retrieve_analysis_context(store, name, token_budget=100_000)
        assert SignalType.pod_logs in context.signal_contents or SignalType.events in context.signal_contents

    def test_respects_token_budget(self):
        store = RAGStore()
        chunks = [
            Chunk(text=f"content {'x' * 200} chunk {i}", file_path=f"logs/pod_{i}.log",
                  signal_type=SignalType.pod_logs, chunk_index=i)
            for i in range(100)
        ]
        name = store.create_collection("test-ret-2", chunks)
        context = retrieve_analysis_context(store, name, token_budget=500)
        total_chars = sum(len(c) for c in context.signal_contents.values())
        assert total_chars <= 3000

    def test_ensures_signal_type_diversity(self):
        store = RAGStore()
        chunks = []
        for st in [SignalType.events, SignalType.pod_logs, SignalType.cluster_info]:
            for i in range(10):
                chunks.append(Chunk(
                    text=f"error failure crash {st.value} {i}",
                    file_path=f"bundle/{st.value}/file_{i}.txt",
                    signal_type=st, chunk_index=i,
                ))
        name = store.create_collection("test-ret-3", chunks)
        context = retrieve_analysis_context(store, name, token_budget=100_000)
        assert len(context.signal_contents) >= 2


class TestRetrieveForQuery:
    def test_returns_formatted_results(self):
        store = RAGStore()
        chunks = [
            Chunk(text="OOM killed container", file_path="logs/pod.log",
                  signal_type=SignalType.pod_logs, chunk_index=0),
        ]
        name = store.create_collection("test-ret-4", chunks)
        results = retrieve_for_query(store, name, "out of memory", max_results=5)
        assert len(results) >= 1
        assert results[0].text == "OOM killed container"
