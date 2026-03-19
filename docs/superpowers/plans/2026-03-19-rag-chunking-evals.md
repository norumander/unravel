# RAG-Enhanced Chunking & Quality Evals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace priority-weighted truncation with semantic retrieval (RAG) and add programmatic quality evals to improve analysis accuracy and chat retrieval.

**Architecture:** Chunk bundle files by content type → embed with local MiniLM model → store in ChromaDB ephemeral → retrieve via diagnostic queries for analysis and semantic search tool for chat → evaluate report quality with programmatic checks (coverage, citation accuracy). All in-memory, session-scoped, no new containers.

**Tech Stack:** ChromaDB (ephemeral), sentence-transformers (all-MiniLM-L6-v2)

**Descoped from spec:** LLM judge evals (actionability, coherence) and LangGraph dependency are deferred. The programmatic checks (coverage, citation accuracy) provide the highest-value quality gates at zero LLM cost. LLM judge evals can be added later once the RAG pipeline is proven. This avoids adding ~15MB of unused dependencies (langgraph, langchain-core) and keeps the eval implementation simple and testable.

**Spec:** `docs/superpowers/specs/2026-03-19-rag-chunking-evals-design.md`

---

## File Structure

### New files

| File | Responsibility |
|---|---|
| `src/backend/app/bundle/chunker.py` | Content-type-aware chunking (JSON, YAML, log, fixed-size fallback) |
| `src/backend/app/rag/__init__.py` | Package init |
| `src/backend/app/rag/embedder.py` | Embed chunks using sentence-transformers, manage ChromaDB collections |
| `src/backend/app/rag/retriever.py` | Diagnostic query retrieval + signal-type-diverse result assembly |
| `src/backend/app/evals/__init__.py` | Package init |
| `src/backend/app/evals/evaluator.py` | Programmatic quality checks (coverage, citation accuracy) |
| `src/backend/tests/unit/test_chunker.py` | Chunker unit tests |
| `src/backend/tests/unit/test_embedder.py` | Embedder unit tests |
| `src/backend/tests/unit/test_retriever.py` | Retriever unit tests |
| `src/backend/tests/unit/test_evaluator.py` | Evaluator unit tests |

### Modified files

| File | What changes |
|---|---|
| `src/backend/pyproject.toml` | Add chromadb, sentence-transformers; install torch CPU-only via Dockerfile |
| `src/backend/Dockerfile` | Pre-download embedding model at build time |
| `src/backend/app/models/schemas.py` | Add `chroma_collection_name` field to Session; add `eval_scores` field to DiagnosticReport |
| `src/backend/app/sessions/store.py` | Add ChromaDB collection cleanup in `delete()` and `_evict_expired()` |
| `src/backend/app/analysis/context.py` | No changes — `estimate_tokens` and `CHARS_PER_TOKEN` are imported by the retriever but the module itself is untouched |
| `src/backend/app/api/routes.py` | Wire RAG into upload/analyze/chat; add `search_bundle` tool; update `CHAT_SYSTEM_PROMPT` reference |
| `src/backend/app/llm/prompts.py` | Update `CHAT_SYSTEM_PROMPT` to mention `search_bundle` tool |
| `.env.example` | Add optional RAG/eval env vars with defaults |

---

## Task 1: Add Dependencies and Update Dockerfile

**Files:**
- Modify: `src/backend/pyproject.toml`
- Modify: `src/backend/Dockerfile`
- Modify: `.env.example`

- [ ] **Step 1: Add new dependencies to pyproject.toml**

Add to the `dependencies` list in `src/backend/pyproject.toml`:

```toml
[project]
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "anthropic>=0.40.0",
    "openai>=1.50.0",
    "pydantic>=2.9.0",
    "sse-starlette>=2.1.0",
    "python-multipart>=0.0.12",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
]
```

- [ ] **Step 2: Update Dockerfile to pre-download embedding model**

Replace the contents of `src/backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install torch CPU-only first (avoids pulling CUDA variant via sentence-transformers)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir $(python -c "import tomllib; f=open('pyproject.toml','rb'); deps=tomllib.load(f)['project']['dependencies']; print(' '.join(deps))")

# Pre-download the embedding model at build time (not runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY app/ app/

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Add optional env vars to .env.example**

Append to `.env.example`:

```
# Optional: RAG and eval tuning (defaults are sensible)
# RAG_CHUNK_SIZE=512
# RAG_CHUNK_OVERLAP=50
# EVAL_THRESHOLD=0.7
```

- [ ] **Step 4: Verify Docker builds**

Run: `docker compose build backend`
Expected: Builds successfully, embedding model downloaded during build.

- [ ] **Step 5: Commit**

```bash
git add src/backend/pyproject.toml src/backend/Dockerfile .env.example
git commit -m "chore: add RAG and eval dependencies, pre-download embedding model [TASK-1]"
```

---

## Task 2: Content-Type-Aware Chunker

**Files:**
- Create: `src/backend/app/bundle/chunker.py`
- Test: `src/backend/tests/unit/test_chunker.py`

- [ ] **Step 1: Write failing tests for fixed-size fallback chunking**

Create `src/backend/tests/unit/test_chunker.py`:

```python
"""Unit tests for content-type-aware chunker."""

import json

from app.bundle.chunker import Chunk, chunk_file
from app.models.schemas import SignalType


class TestFixedSizeChunking:
    """Fixed-size fallback used for cluster_info, node_status, other, and unknown formats."""

    def test_small_file_single_chunk(self):
        content = "short content"
        chunks = chunk_file("bundle/info.txt", content, SignalType.cluster_info)
        assert len(chunks) == 1
        assert chunks[0].text == content
        assert chunks[0].file_path == "bundle/info.txt"
        assert chunks[0].signal_type == SignalType.cluster_info
        assert chunks[0].chunk_index == 0

    def test_large_file_multiple_chunks(self):
        # 512 tokens * 4 chars = 2048 chars per chunk
        content = "x" * 5000
        chunks = chunk_file("bundle/info.txt", content, SignalType.cluster_info)
        assert len(chunks) >= 2
        # All content should be represented
        combined = "".join(c.text for c in chunks)
        assert len(combined) >= len(content)

    def test_chunk_overlap(self):
        content = "x" * 5000
        chunks = chunk_file("bundle/info.txt", content, SignalType.cluster_info)
        if len(chunks) >= 2:
            # Second chunk should start before first chunk ends (overlap)
            first_end = chunks[0].char_end
            second_start = chunks[1].char_start
            assert second_start < first_end

    def test_empty_content_returns_empty(self):
        chunks = chunk_file("bundle/empty.txt", "", SignalType.other)
        assert len(chunks) == 0

    def test_chunk_metadata_correct(self):
        content = "some data"
        chunks = chunk_file("bundle/data.txt", content, SignalType.node_status)
        assert all(c.signal_type == SignalType.node_status for c in chunks)
        assert all(c.file_path == "bundle/data.txt" for c in chunks)
        for i, c in enumerate(chunks):
            assert c.chunk_index == i


class TestJsonEventChunking:
    """JSON array chunking for events signal type."""

    def test_json_array_one_chunk_per_element(self):
        events = [
            {"type": "Warning", "reason": "BackOff", "message": "Back-off restarting"},
            {"type": "Normal", "reason": "Scheduled", "message": "Assigned to node"},
        ]
        content = json.dumps(events)
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) == 2

    def test_json_object_with_items_key(self):
        # Some event files wrap events in {"items": [...]}
        data = {"items": [{"kind": "Event", "message": "OOM"}, {"kind": "Event", "message": "OK"}]}
        content = json.dumps(data)
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) == 2

    def test_invalid_json_falls_back_to_fixed_size(self):
        content = "this is not json {"
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) >= 1  # Falls back to fixed-size

    def test_single_event_single_chunk(self):
        content = json.dumps([{"type": "Warning", "message": "test"}])
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) == 1


class TestYamlResourceChunking:
    """YAML document boundary chunking for resource_definitions."""

    def test_multi_document_yaml(self):
        content = """apiVersion: v1
kind: Pod
metadata:
  name: pod-a
---
apiVersion: v1
kind: Service
metadata:
  name: svc-b
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deploy-c"""
        chunks = chunk_file("bundle/cluster-resources/pods.yaml", content, SignalType.resource_definitions)
        assert len(chunks) == 3

    def test_single_document_yaml(self):
        content = """apiVersion: v1
kind: Pod
metadata:
  name: pod-a"""
        chunks = chunk_file("bundle/cluster-resources/pods.yaml", content, SignalType.resource_definitions)
        assert len(chunks) == 1

    def test_empty_documents_skipped(self):
        content = """---
apiVersion: v1
kind: Pod
---
---
apiVersion: v1
kind: Service"""
        chunks = chunk_file("bundle/cluster-resources/pods.yaml", content, SignalType.resource_definitions)
        assert len(chunks) == 2  # Empty doc skipped


class TestLogChunking:
    """Timestamp-grouped log chunking for pod_logs."""

    def test_log_lines_grouped(self):
        lines = [f"2024-01-15T14:00:{i:02d}Z log message {i}" for i in range(60)]
        content = "\n".join(lines)
        chunks = chunk_file("bundle/logs/pod.log", content, SignalType.pod_logs)
        assert len(chunks) >= 1
        # Each chunk should have multiple lines
        for c in chunks:
            assert "\n" in c.text or len(c.text) < 100

    def test_non_timestamped_logs_fall_back(self):
        content = "\n".join([f"plain log line {i}" for i in range(100)])
        chunks = chunk_file("bundle/logs/pod.log", content, SignalType.pod_logs)
        assert len(chunks) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_chunker.py -v 2>&1 | head -20`
Expected: ImportError — `app.bundle.chunker` does not exist yet.

- [ ] **Step 3: Implement the chunker**

Create `src/backend/app/bundle/chunker.py`:

```python
"""Content-type-aware chunker — splits bundle files into retrieval-friendly chunks."""

import json
import os
import re
from dataclasses import dataclass

from app.models.schemas import SignalType

CHARS_PER_TOKEN = 4
DEFAULT_CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "512"))  # tokens
DEFAULT_CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "50"))  # tokens

# Timestamp patterns common in Kubernetes logs
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
)
_LOG_GROUP_SIZE = 30  # lines per chunk for timestamped logs


@dataclass
class Chunk:
    """A single chunk of text with metadata."""

    text: str
    file_path: str
    signal_type: SignalType
    chunk_index: int
    char_start: int = 0
    char_end: int = 0


def chunk_file(
    file_path: str,
    content: str,
    signal_type: SignalType,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk a file using the appropriate strategy for its signal type.

    Strategies:
    - events (JSON): one chunk per event object
    - resource_definitions (YAML): one chunk per --- document boundary
    - pod_logs (text): group by timestamp window (~30 lines)
    - cluster_info, node_status, other: fixed-size with overlap
    """
    if not content.strip():
        return []

    if signal_type == SignalType.events:
        chunks = _chunk_json_events(content, file_path, signal_type)
        if chunks is not None:
            return chunks

    if signal_type == SignalType.resource_definitions:
        chunks = _chunk_yaml_documents(content, file_path, signal_type)
        if chunks is not None:
            return chunks

    if signal_type == SignalType.pod_logs:
        chunks = _chunk_log_lines(content, file_path, signal_type)
        if chunks is not None:
            return chunks

    return _chunk_fixed_size(content, file_path, signal_type, chunk_size, chunk_overlap)


def _chunk_json_events(
    content: str, file_path: str, signal_type: SignalType
) -> list[Chunk] | None:
    """Split JSON into one chunk per array element. Returns None if parsing fails."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None

    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        items = data["items"]
    else:
        return None

    if not items:
        return None

    chunks = []
    for i, item in enumerate(items):
        text = json.dumps(item, indent=2)
        chunks.append(Chunk(
            text=text,
            file_path=file_path,
            signal_type=signal_type,
            chunk_index=i,
        ))
    return chunks


def _chunk_yaml_documents(
    content: str, file_path: str, signal_type: SignalType
) -> list[Chunk] | None:
    """Split YAML by --- document separators."""
    docs = re.split(r"^---\s*$", content, flags=re.MULTILINE)
    docs = [d.strip() for d in docs if d.strip()]

    if not docs:
        return None

    chunks = []
    for i, doc in enumerate(docs):
        chunks.append(Chunk(
            text=doc,
            file_path=file_path,
            signal_type=signal_type,
            chunk_index=i,
        ))
    return chunks


def _chunk_log_lines(
    content: str, file_path: str, signal_type: SignalType
) -> list[Chunk] | None:
    """Group log lines by timestamp windows."""
    lines = content.split("\n")

    # Check if lines have timestamps — use tighter grouping for timestamped logs
    has_timestamps = sum(1 for line in lines[:20] if _TIMESTAMP_RE.match(line))
    group_size = _LOG_GROUP_SIZE if has_timestamps > len(lines[:20]) * 0.3 else _LOG_GROUP_SIZE * 2

    if len(lines) <= group_size:
        return [Chunk(
            text=content,
            file_path=file_path,
            signal_type=signal_type,
            chunk_index=0,
        )]

    chunks = []
    for i in range(0, len(lines), group_size):
        group = "\n".join(lines[i:i + group_size])
        if group.strip():
            chunks.append(Chunk(
                text=group,
                file_path=file_path,
                signal_type=signal_type,
                chunk_index=len(chunks),
            ))
    return chunks if chunks else None


def _chunk_fixed_size(
    content: str,
    file_path: str,
    signal_type: SignalType,
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """Fixed-size chunking with character overlap."""
    max_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = chunk_overlap * CHARS_PER_TOKEN

    if len(content) <= max_chars:
        return [Chunk(
            text=content,
            file_path=file_path,
            signal_type=signal_type,
            chunk_index=0,
            char_start=0,
            char_end=len(content),
        )]

    chunks = []
    start = 0
    idx = 0
    while start < len(content):
        end = min(start + max_chars, len(content))
        chunks.append(Chunk(
            text=content[start:end],
            file_path=file_path,
            signal_type=signal_type,
            chunk_index=idx,
            char_start=start,
            char_end=end,
        ))
        idx += 1
        next_start = end - overlap_chars
        # If remaining content after overlap is less than overlap_chars,
        # the last chunk already covers it — stop to avoid redundant tiny chunks
        if next_start >= len(content) or len(content) - next_start <= overlap_chars:
            break
        start = next_start
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_chunker.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/bundle/chunker.py src/backend/tests/unit/test_chunker.py
git commit -m "feat: content-type-aware chunker for JSON, YAML, logs, and fixed-size fallback [TASK-2]"
```

---

## Task 3: Embedder and Vector Store

**Files:**
- Create: `src/backend/app/rag/__init__.py`
- Create: `src/backend/app/rag/embedder.py`
- Test: `src/backend/tests/unit/test_embedder.py`

- [ ] **Step 1: Write failing tests for embedder**

Create `src/backend/tests/unit/test_embedder.py`:

```python
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
        # The crash-related chunk should be most relevant
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
        store.delete_collection("nonexistent")  # Should not raise


class TestRAGStoreFallback:
    def test_store_reports_availability(self):
        store = RAGStore()
        assert store.is_available() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_embedder.py -v 2>&1 | head -10`
Expected: ImportError — `app.rag.embedder` does not exist.

- [ ] **Step 3: Create the rag package**

Create `src/backend/app/rag/__init__.py`:

```python
"""RAG (Retrieval Augmented Generation) package for semantic search over bundle content."""

from app.rag.embedder import RAGStore

# Global singleton instance — imported by routes.py and main.py
rag_store = RAGStore()
```

**Note**: The global instance is created here (not in `main.py`) to avoid circular imports. Both `main.py` (for cleanup hook registration) and `routes.py` (for RAG operations) import from `app.rag` without circularity.

- [ ] **Step 4: Implement the embedder**

Create `src/backend/app/rag/embedder.py`:

```python
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
    """A single search result from the vector store."""

    text: str
    file_path: str
    signal_type: SignalType
    chunk_index: int
    score: float


class RAGStore:
    """Manages ChromaDB collections and sentence-transformer embeddings.

    Each session gets its own collection. Collections are ephemeral —
    they live in memory and are destroyed on cleanup.
    """

    def __init__(self) -> None:
        self._client = chromadb.Client()  # Ephemeral, in-memory only
        self._model: SentenceTransformer | None = None
        self._available = True
        try:
            self._model = SentenceTransformer(_MODEL_NAME)
        except Exception:
            logger.warning(
                "Failed to load embedding model '%s'. RAG features disabled — "
                "falling back to priority-weighted truncation.",
                _MODEL_NAME,
                exc_info=True,
            )
            self._available = False

    def is_available(self) -> bool:
        """Return True if the embedding model loaded successfully."""
        return self._available

    def create_collection(
        self, session_id: str, chunks: list[Chunk]
    ) -> str | None:
        """Create a ChromaDB collection and embed all chunks.

        Returns the collection name, or None if chunks is empty.
        """
        if not chunks:
            return None
        if not self._available or self._model is None:
            return None

        collection_name = f"session-{session_id}"
        collection = self._client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

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

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(
            "Created collection '%s' with %d chunks", collection_name, len(chunks)
        )
        return collection_name

    def query(
        self, collection_name: str, query_text: str, n_results: int = 10
    ) -> list[SearchResult]:
        """Query a collection for semantically similar chunks."""
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
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                search_results.append(SearchResult(
                    text=doc,
                    file_path=meta["file_path"],
                    signal_type=SignalType(meta["signal_type"]),
                    chunk_index=meta["chunk_index"],
                    score=1.0 - dist,  # cosine distance → similarity
                ))

        return search_results

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists."""
        try:
            self._client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def delete_collection(self, collection_name: str) -> None:
        """Delete a collection. No-op if it doesn't exist."""
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass  # Collection already deleted or never existed
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_embedder.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/rag/ src/backend/tests/unit/test_embedder.py
git commit -m "feat: RAG store with ChromaDB embeddings and semantic search [TASK-3]"
```

---

## Task 4: Diagnostic Query Retriever

**Files:**
- Create: `src/backend/app/rag/retriever.py`
- Test: `src/backend/tests/unit/test_retriever.py`

- [ ] **Step 1: Write failing tests for retriever**

Create `src/backend/tests/unit/test_retriever.py`:

```python
"""Unit tests for diagnostic query retriever."""

from unittest.mock import MagicMock

from app.bundle.chunker import Chunk
from app.models.schemas import SignalType
from app.rag.embedder import RAGStore, SearchResult
from app.rag.retriever import retrieve_analysis_context, retrieve_for_query


def _make_search_results(signal_types: list[SignalType], n_per_type: int = 3) -> list[SearchResult]:
    results = []
    for st in signal_types:
        for i in range(n_per_type):
            results.append(SearchResult(
                text=f"content for {st.value} chunk {i}",
                file_path=f"bundle/{st.value}/file_{i}.txt",
                signal_type=st,
                chunk_index=i,
                score=0.9 - i * 0.1,
            ))
    return results


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
        # Create many chunks
        chunks = [
            Chunk(text=f"content {'x' * 200} chunk {i}", file_path=f"logs/pod_{i}.log",
                  signal_type=SignalType.pod_logs, chunk_index=i)
            for i in range(100)
        ]
        name = store.create_collection("test-ret-2", chunks)

        context = retrieve_analysis_context(store, name, token_budget=500)
        total_chars = sum(len(c) for c in context.signal_contents.values())
        # Should be roughly within budget (500 tokens * 4 chars = 2000 chars)
        assert total_chars <= 3000  # Some tolerance for headers

    def test_ensures_signal_type_diversity(self):
        store = RAGStore()
        # Create chunks from multiple signal types
        chunks = []
        for st in [SignalType.events, SignalType.pod_logs, SignalType.cluster_info]:
            for i in range(10):
                chunks.append(Chunk(
                    text=f"error failure crash {st.value} {i}",
                    file_path=f"bundle/{st.value}/file_{i}.txt",
                    signal_type=st,
                    chunk_index=i,
                ))
        name = store.create_collection("test-ret-3", chunks)

        context = retrieve_analysis_context(store, name, token_budget=100_000)
        # Should have content from multiple signal types
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_retriever.py -v 2>&1 | head -10`
Expected: ImportError — `app.rag.retriever` does not exist.

- [ ] **Step 3: Implement the retriever**

Create `src/backend/app/rag/retriever.py`:

```python
"""Diagnostic query retriever — retrieves relevant chunks for analysis and chat."""

import logging

from app.analysis.context import CHARS_PER_TOKEN, estimate_tokens
from app.models.schemas import AnalysisContext, BundleFile, BundleManifest, SignalType
from app.rag.embedder import RAGStore, SearchResult

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_BUDGET = 100_000

# Diagnostic queries tuned for Kubernetes support bundle analysis.
DIAGNOSTIC_QUERIES = [
    "pod crash loop backoff restart failure",
    "OOM killed memory limit exceeded",
    "image pull error registry authentication",
    "node not ready disk pressure memory pressure",
    "pending pod scheduling failed insufficient resources",
    "certificate expired TLS handshake error",
    "connection refused timeout network policy",
    "volume mount failed persistent volume claim",
    "RBAC permission denied forbidden",
    "deployment rollout failed replica unavailable",
    "liveness readiness probe failed",
    "DNS resolution failure service discovery",
]

# Minimum percentage of budget reserved for each signal type present.
_MIN_SIGNAL_BUDGET_PCT = 0.05  # 5%


def retrieve_analysis_context(
    store: RAGStore,
    collection_name: str,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    bundle_manifest: BundleManifest | None = None,
) -> AnalysisContext:
    """Retrieve relevant chunks for LLM analysis using diagnostic queries.

    Runs all diagnostic queries, deduplicates and scores results,
    ensures signal type diversity, and assembles into AnalysisContext.
    """
    # Run all diagnostic queries
    all_results: dict[str, SearchResult] = {}  # keyed by chunk id to deduplicate
    hit_counts: dict[str, int] = {}  # how many queries each chunk matched

    for query in DIAGNOSTIC_QUERIES:
        results = store.query(collection_name, query, n_results=10)
        for r in results:
            chunk_id = f"{r.file_path}::{r.chunk_index}"
            if chunk_id not in all_results or r.score > all_results[chunk_id].score:
                all_results[chunk_id] = r
            hit_counts[chunk_id] = hit_counts.get(chunk_id, 0) + 1

    # Score: combine similarity score with multi-query hit bonus
    scored: list[tuple[str, SearchResult, float]] = []
    for chunk_id, result in all_results.items():
        multi_query_bonus = min(hit_counts[chunk_id] * 0.1, 0.5)
        combined_score = result.score + multi_query_bonus
        scored.append((chunk_id, result, combined_score))

    scored.sort(key=lambda x: x[2], reverse=True)

    # Ensure signal type diversity: reserve minimum budget per signal type
    signal_types_present: set[SignalType] = {r.signal_type for _, r, _ in scored}
    min_per_type = max(1, int(token_budget * _MIN_SIGNAL_BUDGET_PCT / 200))  # ~min chunks

    selected: list[SearchResult] = []
    selected_ids: set[str] = set()
    remaining_budget = token_budget

    # First pass: ensure at least min_per_type from each signal type
    for st in signal_types_present:
        type_results = [(cid, r, s) for cid, r, s in scored if r.signal_type == st and cid not in selected_ids]
        for cid, r, _ in type_results[:min_per_type]:
            tokens = estimate_tokens(r.text)
            if tokens <= remaining_budget:
                selected.append(r)
                selected_ids.add(cid)
                remaining_budget -= tokens

    # Second pass: fill remaining budget with highest-scored chunks
    for chunk_id, result, _ in scored:
        if chunk_id in selected_ids:
            continue
        tokens = estimate_tokens(result.text)
        if tokens > remaining_budget:
            continue
        selected.append(result)
        selected_ids.add(chunk_id)
        remaining_budget -= tokens

    # Group by signal type for the prompt
    signal_contents: dict[SignalType, str] = {}
    for result in selected:
        header = f"--- {result.file_path} ---\n"
        content = header + result.text
        if result.signal_type in signal_contents:
            signal_contents[result.signal_type] += "\n\n" + content
        else:
            signal_contents[result.signal_type] = content

    # Build retrieval notes
    type_counts = {}
    for r in selected:
        type_counts[r.signal_type.value] = type_counts.get(r.signal_type.value, 0) + 1
    total_available = len(all_results)
    total_selected = len(selected)
    coverage = ", ".join(f"{k}({v})" for k, v in sorted(type_counts.items()))
    truncation_notes = (
        f"retrieved {total_selected} of {total_available} unique chunks via semantic search; "
        f"signal coverage: {coverage}"
    )

    manifest = bundle_manifest or BundleManifest(total_files=0, total_size_bytes=0, files=[])

    return AnalysisContext(
        signal_contents=signal_contents,
        truncation_notes=truncation_notes,
        manifest=manifest,
    )


def retrieve_for_query(
    store: RAGStore,
    collection_name: str,
    query: str,
    max_results: int = 10,
) -> list[SearchResult]:
    """Retrieve chunks matching a single query — used by the chat search_bundle tool."""
    return store.query(collection_name, query, n_results=max_results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_retriever.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/rag/retriever.py src/backend/tests/unit/test_retriever.py
git commit -m "feat: diagnostic query retriever with signal-type diversity [TASK-4]"
```

---

## Task 5: Update Session Model and Store Cleanup

**Files:**
- Modify: `src/backend/app/models/schemas.py:73-119`
- Modify: `src/backend/app/sessions/store.py:27-51,65-85`
- Modify: `src/backend/tests/unit/test_store.py`
- Modify: `src/backend/tests/unit/test_models.py`

- [ ] **Step 1: Write failing tests for new Session fields**

Add to `src/backend/tests/unit/test_models.py`:

```python
class TestSessionChromaField:
    def test_session_chroma_collection_default_none(self):
        session = Session(
            session_id="test",
            bundle_manifest=BundleManifest(total_files=0, total_size_bytes=0, files=[]),
            extracted_files={},
            classified_signals={},
        )
        assert session.chroma_collection_name is None

    def test_session_chroma_collection_set(self):
        session = Session(
            session_id="test",
            bundle_manifest=BundleManifest(total_files=0, total_size_bytes=0, files=[]),
            extracted_files={},
            classified_signals={},
            chroma_collection_name="session-test",
        )
        assert session.chroma_collection_name == "session-test"


class TestDiagnosticReportEvalScores:
    def test_report_eval_scores_default_none(self):
        report = DiagnosticReport(
            executive_summary="test",
            findings=[],
            signal_types_analyzed=[SignalType.events],
        )
        assert report.eval_scores is None

    def test_report_eval_scores_set(self):
        scores = {"coverage": 0.9, "citation_accuracy": 1.0, "actionability": 0.8, "coherence": 0.85}
        report = DiagnosticReport(
            executive_summary="test",
            findings=[],
            signal_types_analyzed=[SignalType.events],
            eval_scores=scores,
        )
        assert report.eval_scores["coverage"] == 0.9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_models.py::TestSessionChromaField -v`
Expected: FAIL — `chroma_collection_name` field doesn't exist.

- [ ] **Step 3: Add new fields to models**

In `src/backend/app/models/schemas.py`, add `eval_scores` to `DiagnosticReport` (after `timeline` field):

```python
class DiagnosticReport(BaseModel):
    """Structured diagnostic report produced by LLM analysis."""

    executive_summary: str
    findings: list[Finding]
    signal_types_analyzed: list[SignalType]
    truncation_notes: str | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    eval_scores: dict[str, float] | None = None
```

And add `chroma_collection_name` to `Session` (after `chat_history` field):

```python
class Session(BaseModel):
    """In-memory session holding all data for a single bundle analysis."""

    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    bundle_manifest: BundleManifest
    extracted_files: dict[str, bytes]
    classified_signals: dict[SignalType, list[BundleFile]]
    report: DiagnosticReport | None = None
    analyzing: bool = False
    chat_history: list[ChatMessage] = Field(default_factory=list)
    chroma_collection_name: str | None = None
```

- [ ] **Step 4: Run model tests**

Run: `cd src/backend && python -m pytest tests/unit/test_models.py -v`
Expected: All tests PASS (including new ones).

- [ ] **Step 5: Update session store cleanup — targeted edits**

In `src/backend/app/sessions/store.py`, apply these changes:

**Add imports** (after existing imports at top of file):
```python
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)
```

**Add cleanup fields and methods to `SessionStore.__init__`** (add after `self._sessions` line):
```python
self._cleanup_hooks: list[Callable[[Session], None]] = []
```

**Add two new methods** (after `__init__`, before `create`):
```python
def register_cleanup_hook(self, hook: Callable[[Session], None]) -> None:
    """Register a callback that runs before a session is deleted."""
    self._cleanup_hooks.append(hook)

def _run_cleanup(self, session: Session) -> None:
    """Run all cleanup hooks for a session."""
    for hook in self._cleanup_hooks:
        try:
            hook(session)
        except Exception:
            logger.warning("Cleanup hook failed for session %s", session.session_id, exc_info=True)
```

**In `create()`** — add `self._run_cleanup(self._sessions[oldest_id])` before `del self._sessions[oldest_id]` in the eviction while loop.

**In `delete()`** — add `self._run_cleanup(self._sessions[session_id])` before `del self._sessions[session_id]`.

**In `_evict_expired()`** — add `self._run_cleanup(self._sessions[sid])` before `del self._sessions[sid]` in the for loop.

- [ ] **Step 6: Run all store tests**

Run: `cd src/backend && python -m pytest tests/unit/test_store.py -v`
Expected: All tests PASS (cleanup hooks are additive — existing behavior unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/backend/app/models/schemas.py src/backend/app/sessions/store.py \
       src/backend/tests/unit/test_models.py src/backend/tests/unit/test_store.py
git commit -m "feat: add chroma_collection_name to Session, eval_scores to Report, cleanup hooks to store [TASK-5]"
```

---

## Task 6: Wire RAG into Upload and Analysis Pipeline

**Files:**
- Modify: `src/backend/app/api/routes.py:65-251`
- Modify: `src/backend/app/analysis/context.py`
- Modify: `src/backend/app/main.py`

- [ ] **Step 1: Create global RAG store and register cleanup hook**

In `src/backend/app/main.py`, add after the app creation:

```python
from app.rag import rag_store
from app.sessions.store import session_store

# Register cleanup hook to delete ChromaDB collections when sessions expire
def _cleanup_chroma(session):
    if session.chroma_collection_name:
        rag_store.delete_collection(session.chroma_collection_name)

session_store.register_cleanup_hook(_cleanup_chroma)
```

- [ ] **Step 2: Add RAG indexing to upload endpoint**

In `src/backend/app/api/routes.py`, after `session = session_store.create(...)` in the upload endpoint, add chunking and embedding:

```python
from app.bundle.chunker import chunk_file
from app.rag import rag_store

# Inside upload_bundle, after session_store.create():
rag = rag_store
if rag.is_available():
    chunks = []
    for bf in manifest.files:
        file_content = extracted_files.get(bf.path)
        if file_content is None:
            continue
        text = file_content.decode("utf-8", errors="replace")
        chunks.extend(chunk_file(bf.path, text, bf.signal_type))

    collection_name = rag.create_collection(session.session_id, chunks)
    session.chroma_collection_name = collection_name

    if collection_name:
        response_content["chunks_indexed"] = len(chunks)
```

- [ ] **Step 3: Update analysis to use RAG retriever when available**

In `src/backend/app/api/routes.py`, inside `event_generator()` for the analyze endpoint, replace the `assemble_context` call:

```python
from app.rag.retriever import retrieve_analysis_context

# Replace:
# context = assemble_context(session.classified_signals, session.extracted_files)
# With:
rag = rag_store
if rag.is_available() and session.chroma_collection_name:
    context = retrieve_analysis_context(
        rag, session.chroma_collection_name,
        bundle_manifest=session.bundle_manifest,
    )
else:
    context = assemble_context(session.classified_signals, session.extracted_files)
```

- [ ] **Step 4: Run existing tests to verify nothing is broken**

Run: `cd src/backend && python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS (RAG is additive — falls back when store not available).

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/main.py src/backend/app/api/routes.py src/backend/app/analysis/context.py
git commit -m "feat: wire RAG indexing into upload and analysis pipeline with fallback [TASK-6]"
```

---

## Task 7: Add search_bundle Chat Tool

**Files:**
- Modify: `src/backend/app/api/routes.py:254-382`
- Modify: `src/backend/app/llm/prompts.py:52-59`

- [ ] **Step 1: Add SEARCH_BUNDLE_TOOL definition**

In `src/backend/app/api/routes.py`, add after `GET_FILE_CONTENTS_TOOL`:

```python
SEARCH_BUNDLE_TOOL = {
    "name": "search_bundle",
    "description": (
        "Semantically search the support bundle for content related to a query. "
        "Returns the most relevant chunks with file paths and context. "
        "Use this FIRST to find relevant content, then use get_file_contents "
        "only if you need the complete file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what you're looking for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of chunks to return (default 10).",
            },
        },
        "required": ["query"],
    },
}
```

- [ ] **Step 2: Update tool_handler in chat endpoint**

In the chat endpoint's `tool_handler` function, add the `search_bundle` case:

```python
from app.rag.retriever import retrieve_for_query

def tool_handler(name: str, arguments: dict) -> str:
    if name == "get_file_contents":
        file_path = arguments.get("file_path", "")
        content = session.extracted_files.get(file_path)
        if content is None:
            return f"File not found in bundle: {file_path}"
        return content.decode("utf-8", errors="replace")
    if name == "search_bundle":
        rag = rag_store
        if not rag.is_available() or not session.chroma_collection_name:
            return "Semantic search is not available. Use get_file_contents instead."
        query = arguments.get("query", "")
        max_results = arguments.get("max_results", 10)
        results = retrieve_for_query(
            rag, session.chroma_collection_name, query, max_results=max_results
        )
        if not results:
            return f"No results found for query: {query}"
        parts = []
        for r in results:
            parts.append(
                f"--- {r.file_path} ({r.signal_type.value}, relevance: {r.score:.2f}) ---\n{r.text}"
            )
        return "\n\n".join(parts)
    return f"Unknown tool: {name}"
```

- [ ] **Step 3: Pass both tools to the LLM**

In the chat endpoint, update the tools list:

```python
tools = [GET_FILE_CONTENTS_TOOL]
rag = rag_store
if rag.is_available() and session.chroma_collection_name:
    tools = [SEARCH_BUNDLE_TOOL, GET_FILE_CONTENTS_TOOL]
```

- [ ] **Step 4: Update CHAT_SYSTEM_PROMPT**

In `src/backend/app/llm/prompts.py`, update the chat system prompt:

```python
CHAT_SYSTEM_PROMPT = """You are an expert Kubernetes diagnostician helping investigate issues \
found in a support bundle. You have access to the diagnostic report and bundle manifest.

When investigating, use the search_bundle tool FIRST to find relevant content semantically. \
If you need the complete file after finding relevant chunks, use get_file_contents.

Be specific and reference file paths, pod names, and error messages when relevant. \
If you're uncertain, say so and suggest what to search for."""
```

- [ ] **Step 5: Run full test suite**

Run: `cd src/backend && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/api/routes.py src/backend/app/llm/prompts.py
git commit -m "feat: add search_bundle semantic search tool for chat [TASK-7]"
```

---

## Task 8: LangGraph Quality Evaluator

**Files:**
- Create: `src/backend/app/evals/__init__.py`
- Create: `src/backend/app/evals/evaluator.py`
- Test: `src/backend/tests/unit/test_evaluator.py`

- [ ] **Step 1: Write failing tests for programmatic eval checks**

Create `src/backend/tests/unit/test_evaluator.py`:

```python
"""Unit tests for LangGraph quality evaluator."""

from app.evals.evaluator import (
    check_citation_accuracy,
    check_coverage,
    EvalResult,
)
from app.models.schemas import (
    DiagnosticReport,
    Finding,
    Severity,
    SignalType,
    SourceCitation,
)


def _make_report(
    signal_types: list[SignalType],
    findings_with_sources: list[tuple[str, list[str]]] | None = None,
) -> DiagnosticReport:
    findings = []
    if findings_with_sources:
        for title, source_paths in findings_with_sources:
            findings.append(Finding(
                severity=Severity.warning,
                title=title,
                description="desc",
                root_cause="cause",
                remediation="fix",
                source_signals=[SignalType.events],
                sources=[SourceCitation(file_path=p, excerpt="...") for p in source_paths],
            ))
    return DiagnosticReport(
        executive_summary="summary",
        findings=findings,
        signal_types_analyzed=signal_types,
    )


class TestCheckCoverage:
    def test_full_coverage_score_1(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([SignalType.events, SignalType.pod_logs])
        result = check_coverage(report, bundle_types)
        assert result.score == 1.0

    def test_partial_coverage_score_proportional(self):
        bundle_types = {SignalType.events, SignalType.pod_logs, SignalType.cluster_info}
        report = _make_report([SignalType.events])
        result = check_coverage(report, bundle_types)
        assert 0.3 <= result.score <= 0.4  # 1/3

    def test_no_coverage_score_0(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([])
        result = check_coverage(report, bundle_types)
        assert result.score == 0.0

    def test_coverage_issues_list_missing_types(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([SignalType.events])
        result = check_coverage(report, bundle_types)
        assert "pod_logs" in result.issues[0]


class TestCheckCitationAccuracy:
    def test_all_citations_valid(self):
        extracted_files = {"bundle/events.json": b"data", "bundle/logs/pod.log": b"data"}
        report = _make_report(
            [SignalType.events],
            [("issue", ["bundle/events.json", "bundle/logs/pod.log"])],
        )
        result = check_citation_accuracy(report, extracted_files)
        assert result.score == 1.0

    def test_some_citations_invalid(self):
        extracted_files = {"bundle/events.json": b"data"}
        report = _make_report(
            [SignalType.events],
            [("issue", ["bundle/events.json", "bundle/nonexistent.log"])],
        )
        result = check_citation_accuracy(report, extracted_files)
        assert result.score == 0.5

    def test_no_citations_score_1(self):
        """Reports with no source citations shouldn't be penalized here."""
        report = _make_report([SignalType.events])
        result = check_citation_accuracy(report, {})
        assert result.score == 1.0

    def test_all_citations_invalid(self):
        report = _make_report(
            [SignalType.events],
            [("issue", ["fake/path1.txt", "fake/path2.txt"])],
        )
        result = check_citation_accuracy(report, {})
        assert result.score == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_evaluator.py -v 2>&1 | head -10`
Expected: ImportError — `app.evals.evaluator` does not exist.

- [ ] **Step 3: Create the evals package**

Create `src/backend/app/evals/__init__.py`:

```python
"""Evaluation package for LLM output quality assessment."""
```

- [ ] **Step 4: Implement the evaluator**

Create `src/backend/app/evals/evaluator.py`:

```python
"""LangGraph quality evaluator — scores diagnostic reports and triggers retries."""

import json
import logging
import os
from dataclasses import dataclass, field

from app.models.schemas import DiagnosticReport, SignalType

logger = logging.getLogger(__name__)

EVAL_THRESHOLD = float(os.environ.get("EVAL_THRESHOLD", "0.7"))


@dataclass
class EvalResult:
    """Result of a single evaluation dimension."""

    dimension: str
    score: float  # 0.0 to 1.0
    issues: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """Composite evaluation result across all dimensions."""

    results: list[EvalResult]
    composite_score: float
    passed: bool

    def to_dict(self) -> dict:
        return {
            "composite_score": round(self.composite_score, 3),
            "passed": self.passed,
            "dimensions": {
                r.dimension: {"score": round(r.score, 3), "issues": r.issues}
                for r in self.results
            },
        }


def check_coverage(
    report: DiagnosticReport,
    bundle_signal_types: set[SignalType],
) -> EvalResult:
    """Check if the report analyzed all signal types present in the bundle."""
    if not bundle_signal_types:
        return EvalResult(dimension="coverage", score=1.0)

    analyzed = set(report.signal_types_analyzed)
    # Exclude 'other' from coverage check — it's a catch-all
    relevant_types = bundle_signal_types - {SignalType.other}
    if not relevant_types:
        return EvalResult(dimension="coverage", score=1.0)

    covered = analyzed & relevant_types
    score = len(covered) / len(relevant_types)

    issues = []
    missing = relevant_types - covered
    if missing:
        issues.append(
            f"Signal types not analyzed: {', '.join(st.value for st in missing)}"
        )

    return EvalResult(dimension="coverage", score=score, issues=issues)


def check_citation_accuracy(
    report: DiagnosticReport,
    extracted_files: dict[str, bytes],
) -> EvalResult:
    """Check if source citations reference files that exist in the bundle."""
    all_citations = []
    for finding in report.findings:
        if finding.sources:
            all_citations.extend(finding.sources)

    if not all_citations:
        return EvalResult(dimension="citation_accuracy", score=1.0)

    valid = sum(1 for c in all_citations if c.file_path in extracted_files)
    score = valid / len(all_citations)

    issues = []
    invalid_paths = [c.file_path for c in all_citations if c.file_path not in extracted_files]
    if invalid_paths:
        issues.append(f"Invalid file paths in citations: {', '.join(invalid_paths[:5])}")

    return EvalResult(dimension="citation_accuracy", score=score, issues=issues)


def run_programmatic_evals(
    report: DiagnosticReport,
    bundle_signal_types: set[SignalType],
    extracted_files: dict[str, bytes],
) -> EvalReport:
    """Run the free programmatic evaluation checks.

    LLM-based judge checks (actionability, coherence) are run separately
    and only if these programmatic checks pass.
    """
    coverage = check_coverage(report, bundle_signal_types)
    citation = check_citation_accuracy(report, extracted_files)

    results = [coverage, citation]
    composite = sum(r.score for r in results) / len(results)
    passed = composite >= EVAL_THRESHOLD

    return EvalReport(results=results, composite_score=composite, passed=passed)


def build_retry_feedback(eval_report: EvalReport) -> str:
    """Build feedback string for retry prompt when eval score is below threshold."""
    parts = [
        f"Your previous report scored {eval_report.composite_score:.2f} "
        f"(threshold: {EVAL_THRESHOLD}). Specific issues:"
    ]
    for result in eval_report.results:
        if result.issues:
            parts.append(f"- {result.dimension}: {'; '.join(result.issues)}")

    parts.append(
        "\nPlease improve your analysis. Ensure you analyze ALL signal types "
        "present in the bundle and cite actual file paths from the manifest."
    )
    return "\n".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_evaluator.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/evals/ src/backend/tests/unit/test_evaluator.py
git commit -m "feat: programmatic quality evaluator with coverage and citation checks [TASK-8]"
```

---

## Task 9: Wire Evaluator into Analysis Pipeline

**Files:**
- Modify: `src/backend/app/api/routes.py:114-251`

- [ ] **Step 1: Add eval step after report parsing**

In the analyze endpoint's `event_generator()`, after the report is parsed successfully (after `session.report = report`), add:

```python
from app.evals.evaluator import run_programmatic_evals, build_retry_feedback

# After report is parsed:
bundle_signal_types = {
    st for st, files in session.classified_signals.items() if files
}
eval_report = run_programmatic_evals(
    report, bundle_signal_types, session.extracted_files
)

# Stream eval scores to frontend
yield {"data": json.dumps({
    "type": "eval_scores",
    **eval_report.to_dict(),
})}

# Attach eval scores to report
report.eval_scores = {
    r.dimension: r.score for r in eval_report.results
}
report.eval_scores["composite"] = eval_report.composite_score
session.report = report

# Retry if below threshold (max 1 retry)
if not eval_report.passed:
    feedback = build_retry_feedback(eval_report)
    yield {"data": json.dumps({
        "type": "progress",
        "stage": "retrying",
        "reason": f"Score {eval_report.composite_score:.2f} below threshold",
    })}

    # Re-run analysis with feedback appended to context
    # (reuse the same context + feedback as additional instruction)
    collected_retry = ""
    try:
        active = fallback if used_fallback else provider
        async for chunk in active.analyze(context, extra_instruction=feedback):
            collected_retry += chunk
            yield {"data": json.dumps({"type": "chunk", "content": chunk})}

        cleaned_retry = _strip_markdown_fences(collected_retry)
        cleaned_retry = _sanitize_signal_types(cleaned_retry)
        retry_report = DiagnosticReport.model_validate_json(cleaned_retry)

        # Re-evaluate
        retry_eval = run_programmatic_evals(
            retry_report, bundle_signal_types, session.extracted_files
        )

        # Keep the better report
        if retry_eval.composite_score > eval_report.composite_score:
            retry_report.eval_scores = {
                r.dimension: r.score for r in retry_eval.results
            }
            retry_report.eval_scores["composite"] = retry_eval.composite_score
            session.report = retry_report
            report = retry_report

            yield {"data": json.dumps({
                "type": "eval_scores",
                **retry_eval.to_dict(),
            })}
    except Exception as exc:
        logger.warning("Retry analysis failed: %s", exc)
        # Keep original report
```

**Note**: The `analyze` method needs an optional `extra_instruction` parameter. This requires a small modification to the provider interface and both provider implementations.

- [ ] **Step 2: Add extra_instruction parameter to provider interface**

In `src/backend/app/llm/provider.py`, update the abstract method:

```python
@abstractmethod
async def analyze(
    self, context: AnalysisContext, extra_instruction: str | None = None
) -> AsyncIterator[str]:
```

- [ ] **Step 3: Update AnthropicProvider.analyze()**

In `src/backend/app/llm/anthropic_provider.py`, replace the `analyze` method (currently lines 50-69):

```python
async def analyze(
    self, context: AnalysisContext, extra_instruction: str | None = None
) -> AsyncIterator[str]:
    """Stream analysis of bundle content using Claude."""
    user_prompt = build_analysis_prompt(context)
    if extra_instruction:
        user_prompt += f"\n\n## Additional Instructions\n\n{extra_instruction}"

    try:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=get_max_output_tokens(),
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

            response = await stream.get_final_message()
            self._last_input_tokens = response.usage.input_tokens
            self._last_output_tokens = response.usage.output_tokens

    except Exception as e:
        raise _map_anthropic_error(e) from e
```

- [ ] **Step 4: Update OpenAIProvider.analyze()**

In `src/backend/app/llm/openai_provider.py`, apply the same change to `analyze()` — add `extra_instruction: str | None = None` parameter, and append to `user_prompt` if provided. The rest of the method body stays the same.

- [ ] **Step 5: Run full test suite**

Run: `cd src/backend && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/api/routes.py src/backend/app/llm/provider.py \
       src/backend/app/llm/anthropic_provider.py src/backend/app/llm/openai_provider.py
git commit -m "feat: wire quality evaluator into analysis pipeline with retry [TASK-9]"
```

---

## Task 10: Frontend Progress Event Handling

**Files:**
- Modify: `src/frontend/src/hooks/useSSE.ts` (or equivalent SSE hook)
- Modify: `src/frontend/src/components/ReportPhase.tsx` (or equivalent progress component)

- [ ] **Step 1: Add `progress` and `eval_scores` event types to SSE hook**

Find the SSE event switch statement and add handlers for the new event types. The handler should pass stage/scores data to the component state.

- [ ] **Step 2: Display indexing and evaluation stages in the loading UI**

Add stage labels to the progress stepper for "Indexing bundle..." and "Evaluating report quality..."

- [ ] **Step 3: Optionally display eval scores on the report**

If eval_scores are present on the report, show a small confidence indicator (e.g., "Analysis confidence: 87%").

- [ ] **Step 4: Run frontend tests**

Run: `cd src/frontend && npm run test`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/
git commit -m "feat: handle RAG progress and eval score events in frontend [TASK-10]"
```

---

## Task 11: Integration Test and Docker Verification

**Files:**
- Modify: `src/backend/tests/integration/test_api.py`

- [ ] **Step 1: Add integration test for RAG-enhanced upload/analyze flow**

Add a test that uploads a bundle, verifies `chunks_indexed` in the response, and confirms the analyze endpoint returns a report.

- [ ] **Step 2: Run full backend test suite**

Run: `cd src/backend && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS.

- [ ] **Step 3: Rebuild and test Docker**

Run: `docker compose up --build -d && docker compose logs -f backend 2>&1 | head -30`
Expected: Backend starts, embedding model loads, health check passes.

- [ ] **Step 4: Manual smoke test**

Upload a test bundle via the UI, verify analysis runs and produces a report. Try chat with a question and verify `search_bundle` tool is used.

- [ ] **Step 5: Commit**

```bash
git add src/backend/tests/integration/
git commit -m "test: add integration tests for RAG-enhanced analysis pipeline [TASK-11]"
```

---

## Task 12: Update Documentation

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Update ARCHITECTURE.md with RAG components**

Add the new modules to the component diagram and describe the RAG pipeline.

- [ ] **Step 2: Verify .env.example has all optional vars documented**

Confirm `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `EVAL_THRESHOLD` are listed with comments.

- [ ] **Step 3: Update README with any new setup notes**

Note the increased Docker image size and first-build time. No new required env vars.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md .env.example README.md
git commit -m "docs: update architecture and README for RAG and eval pipeline [TASK-12]"
```
