# Session Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a session explorer dashboard as the landing page so SREs can browse, preview, and re-read past analyses.

**Architecture:** New `SessionPersistence` class writes analysis results to JSON files on disk (index + per-session directories). New API endpoints expose CRUD. Frontend gains an `'explorer'` phase with a table view and detail panel. Existing in-memory `SessionStore` stays unchanged.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), JSON file storage, Docker named volume.

**Spec:** `docs/superpowers/specs/2026-03-21-session-explorer-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/backend/app/sessions/persistence.py` | `SessionPersistence` class — JSON-based CRUD for session history |
| `src/backend/app/sessions/metadata.py` | `extract_bundle_metadata()` — pull cluster/k8s/namespace info from bundle files |
| `src/backend/app/api/session_routes.py` | API endpoints: `GET/PATCH/DELETE /api/sessions` |
| `src/backend/tests/unit/test_persistence.py` | Unit tests for `SessionPersistence` |
| `src/backend/tests/unit/test_metadata.py` | Unit tests for `extract_bundle_metadata` |
| `src/backend/tests/unit/test_session_routes.py` | API route tests |
| `src/frontend/src/components/SessionExplorer.tsx` | Dashboard table + stats bar + filters |
| `src/frontend/src/components/SessionDetail.tsx` | Slide-out detail panel |

### Modified Files

| File | Changes |
|------|---------|
| `src/backend/app/models/schemas.py` | Add Pydantic models: `SessionSummary`, `BundleMetadata`, `FindingSummary`, `PersistedSession` |
| `src/backend/app/api/routes.py` | Hook `SessionPersistence.save_session()` into analyze endpoint; append chat messages to persistence |
| `src/backend/app/main.py` | Register session API routes |
| `src/frontend/src/App.tsx` | Add `'explorer'` phase, navigation handlers, saved-session loading |
| `src/frontend/src/types/api.ts` | Add TypeScript types for session explorer |
| `docker-compose.yml` | Add `session-data` named volume |

---

## Task 1: Persistence Data Models

**Files:**
- Modify: `src/backend/app/models/schemas.py`
- Test: `src/backend/tests/unit/test_persistence.py` (create)

- [ ] **Step 1: Write tests for new models**

Create `src/backend/tests/unit/test_persistence.py`:

```python
"""Tests for session persistence data models."""

import pytest
from datetime import datetime, UTC
from app.models.schemas import (
    FindingSummary,
    BundleMetadata,
    LLMMetaSummary,
    SessionSummary,
)


class TestFindingSummary:
    def test_create_with_valid_severity(self):
        f = FindingSummary(severity="critical", title="CrashLoopBackOff")
        assert f.severity == "critical"
        assert f.title == "CrashLoopBackOff"

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValueError):
            FindingSummary(severity="unknown", title="test")


class TestBundleMetadata:
    def test_defaults_to_empty(self):
        meta = BundleMetadata()
        assert meta.cluster is None
        assert meta.namespaces == []
        assert meta.k8s_version is None
        assert meta.node_count is None

    def test_with_all_fields(self):
        meta = BundleMetadata(
            cluster="prod-east-1",
            namespaces=["default", "kube-system"],
            k8s_version="v1.28.4",
            node_count=3,
        )
        assert meta.cluster == "prod-east-1"
        assert len(meta.namespaces) == 2


class TestLLMMetaSummary:
    def test_create(self):
        m = LLMMetaSummary(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=3200,
        )
        assert m.provider == "anthropic"
        assert m.latency_ms == 3200


class TestSessionSummary:
    def test_create_completed_session(self):
        s = SessionSummary(
            id="abc-123",
            bundle_name="test.tar.gz",
            file_size=1024,
            timestamp=datetime.now(UTC).isoformat(),
            status="completed",
        )
        assert s.status == "completed"
        assert s.notes == ""
        assert s.tags == []
        assert s.findings_summary == []

    def test_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            SessionSummary(
                id="x",
                bundle_name="t.tar.gz",
                file_size=0,
                timestamp=datetime.now(UTC).isoformat(),
                status="invalid",
            )

    def test_serialization_roundtrip(self):
        s = SessionSummary(
            id="abc-123",
            bundle_name="test.tar.gz",
            file_size=1024,
            timestamp=datetime.now(UTC).isoformat(),
            status="completed",
            bundle_metadata=BundleMetadata(cluster="prod"),
            findings_summary=[
                FindingSummary(severity="critical", title="OOM")
            ],
        )
        data = s.model_dump()
        restored = SessionSummary(**data)
        assert restored.id == s.id
        assert restored.bundle_metadata.cluster == "prod"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_persistence.py -v`
Expected: ImportError — models don't exist yet

- [ ] **Step 3: Add models to schemas.py**

Add to `src/backend/app/models/schemas.py` after the existing `ChatMessage` class (around line 98):

```python
class FindingSummary(BaseModel):
    """Lightweight finding for session index — severity + title only."""

    severity: Literal["critical", "warning", "info"]
    title: str


class BundleMetadata(BaseModel):
    """Auto-extracted metadata from the support bundle."""

    cluster: str | None = None
    namespaces: list[str] = Field(default_factory=list)
    k8s_version: str | None = None
    node_count: int | None = None


class LLMMetaSummary(BaseModel):
    """LLM call metadata for session persistence."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class SessionSummary(BaseModel):
    """Session index entry — lightweight data for the dashboard table."""

    id: str
    bundle_name: str
    file_size: int
    timestamp: str
    status: Literal["completed", "error"]
    bundle_metadata: BundleMetadata = Field(default_factory=BundleMetadata)
    findings_summary: list[FindingSummary] = Field(default_factory=list)
    llm_meta: LLMMetaSummary | None = None
    eval_score: float | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
```

Add `Literal` to the `typing` import at the top of the file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_persistence.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/models/schemas.py src/backend/tests/unit/test_persistence.py
git commit -m "feat(models): add session persistence data models [TASK-13]"
```

---

## Task 2: SessionPersistence Class

**Files:**
- Create: `src/backend/app/sessions/persistence.py`
- Test: `src/backend/tests/unit/test_persistence.py` (extend)

- [ ] **Step 1: Write tests for SessionPersistence CRUD**

Append to `src/backend/tests/unit/test_persistence.py`:

```python
import json
import os
import tempfile
from app.sessions.persistence import SessionPersistence
from app.models.schemas import SessionSummary, BundleMetadata, FindingSummary


class TestSessionPersistence:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = SessionPersistence(data_dir=self.tmpdir)

    def _make_summary(self, session_id="s1", status="completed"):
        return SessionSummary(
            id=session_id,
            bundle_name="test.tar.gz",
            file_size=1024,
            timestamp="2026-03-21T12:00:00Z",
            status=status,
            bundle_metadata=BundleMetadata(cluster="prod"),
            findings_summary=[
                FindingSummary(severity="critical", title="OOM")
            ],
        )

    def test_save_and_list(self):
        summary = self._make_summary()
        report = {"executive_summary": "Test report"}
        self.store.save_session(summary, report=report)

        sessions = self.store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].id == "s1"

    def test_save_creates_session_directory(self):
        summary = self._make_summary()
        self.store.save_session(summary, report={"summary": "test"})
        assert os.path.isdir(os.path.join(self.tmpdir, "s1"))
        assert os.path.isfile(os.path.join(self.tmpdir, "s1", "report.json"))

    def test_get_session_returns_full_data(self):
        summary = self._make_summary()
        report = {"executive_summary": "Full report"}
        self.store.save_session(summary, report=report)

        result = self.store.get_session("s1")
        assert result["summary"].id == "s1"
        assert result["report"]["executive_summary"] == "Full report"
        assert result["chat"] == []

    def test_get_session_not_found_raises(self):
        with pytest.raises(KeyError):
            self.store.get_session("nonexistent")

    def test_update_session_notes(self):
        self.store.save_session(self._make_summary())
        self.store.update_session("s1", notes="Customer ACME")

        sessions = self.store.list_sessions()
        assert sessions[0].notes == "Customer ACME"

    def test_update_session_tags(self):
        self.store.save_session(self._make_summary())
        self.store.update_session("s1", tags=["urgent", "acme"])

        sessions = self.store.list_sessions()
        assert sessions[0].tags == ["urgent", "acme"]

    def test_delete_session(self):
        self.store.save_session(self._make_summary(), report={"x": 1})
        self.store.delete_session("s1")

        assert self.store.list_sessions() == []
        assert not os.path.exists(os.path.join(self.tmpdir, "s1"))

    def test_delete_nonexistent_raises(self):
        with pytest.raises(KeyError):
            self.store.delete_session("nope")

    def test_multiple_sessions_ordered_by_timestamp(self):
        s1 = self._make_summary("s1")
        s1.timestamp = "2026-03-20T12:00:00Z"
        s2 = self._make_summary("s2")
        s2.timestamp = "2026-03-21T12:00:00Z"
        self.store.save_session(s1)
        self.store.save_session(s2)

        sessions = self.store.list_sessions()
        assert sessions[0].id == "s2"  # most recent first
        assert sessions[1].id == "s1"

    def test_append_chat_message(self):
        self.store.save_session(self._make_summary())
        self.store.append_chat("s1", {"role": "user", "content": "hello"})
        self.store.append_chat("s1", {"role": "assistant", "content": "hi"})

        result = self.store.get_session("s1")
        assert len(result["chat"]) == 2
        assert result["chat"][0]["role"] == "user"

    def test_empty_index_on_fresh_store(self):
        assert self.store.list_sessions() == []

    def test_atomic_write_creates_valid_json(self):
        self.store.save_session(self._make_summary())
        index_path = os.path.join(self.tmpdir, "sessions.json")
        with open(index_path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_persistence.py::TestSessionPersistence -v`
Expected: ImportError — `SessionPersistence` doesn't exist

- [ ] **Step 3: Implement SessionPersistence**

Create `src/backend/app/sessions/persistence.py`:

```python
"""File-based session persistence — JSON index + per-session directories."""

import json
import logging
import os
import shutil
import tempfile

from app.models.schemas import SessionSummary

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "/app/data/sessions"


class SessionPersistence:
    """Persists completed session data to JSON files.

    Separate from the in-memory SessionStore — this writes durable records
    of finished analyses, not active session runtime state.

    Storage layout:
        {data_dir}/sessions.json         — index of all sessions
        {data_dir}/{session_id}/report.json  — full analysis report
        {data_dir}/{session_id}/chat.json    — chat transcript
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = data_dir or os.environ.get(
            "SESSION_DATA_DIR", DEFAULT_DATA_DIR
        )
        os.makedirs(self._data_dir, exist_ok=True)
        self._index_path = os.path.join(self._data_dir, "sessions.json")

    def _read_index(self) -> list[dict]:
        if not os.path.exists(self._index_path):
            return []
        with open(self._index_path) as f:
            return json.load(f)

    def _write_index(self, entries: list[dict]) -> None:
        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=self._data_dir, suffix=".json.tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(entries, f, indent=2)
            os.replace(tmp_path, self._index_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def save_session(
        self,
        summary: SessionSummary,
        report: dict | None = None,
        chat: list[dict] | None = None,
    ) -> None:
        """Save a session summary to the index and write report/chat files."""
        entries = self._read_index()
        entries.append(summary.model_dump())
        self._write_index(entries)

        session_dir = os.path.join(self._data_dir, summary.id)
        os.makedirs(session_dir, exist_ok=True)

        if report is not None:
            report_path = os.path.join(session_dir, "report.json")
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

        chat_path = os.path.join(session_dir, "chat.json")
        with open(chat_path, "w") as f:
            json.dump(chat or [], f)

    def list_sessions(self) -> list[SessionSummary]:
        """Return all sessions, most recent first."""
        entries = self._read_index()
        sessions = [SessionSummary(**e) for e in entries]
        sessions.sort(key=lambda s: s.timestamp, reverse=True)
        return sessions

    def get_session(self, session_id: str) -> dict:
        """Load full session data: summary + report + chat."""
        entries = self._read_index()
        match = next((e for e in entries if e["id"] == session_id), None)
        if match is None:
            raise KeyError(f"Session {session_id} not found")

        session_dir = os.path.join(self._data_dir, session_id)
        report = {}
        report_path = os.path.join(session_dir, "report.json")
        if os.path.exists(report_path):
            with open(report_path) as f:
                report = json.load(f)

        chat = []
        chat_path = os.path.join(session_dir, "chat.json")
        if os.path.exists(chat_path):
            with open(chat_path) as f:
                chat = json.load(f)

        return {
            "summary": SessionSummary(**match),
            "report": report,
            "chat": chat,
        }

    def update_session(
        self,
        session_id: str,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> SessionSummary:
        """Update mutable fields (notes, tags) on a session."""
        entries = self._read_index()
        match = next((e for e in entries if e["id"] == session_id), None)
        if match is None:
            raise KeyError(f"Session {session_id} not found")

        if notes is not None:
            match["notes"] = notes
        if tags is not None:
            match["tags"] = tags

        self._write_index(entries)
        return SessionSummary(**match)

    def delete_session(self, session_id: str) -> None:
        """Remove a session from the index and delete its data directory."""
        entries = self._read_index()
        original_len = len(entries)
        entries = [e for e in entries if e["id"] != session_id]
        if len(entries) == original_len:
            raise KeyError(f"Session {session_id} not found")

        self._write_index(entries)

        session_dir = os.path.join(self._data_dir, session_id)
        if os.path.isdir(session_dir):
            shutil.rmtree(session_dir)

    def append_chat(self, session_id: str, message: dict) -> None:
        """Append a single chat message to the session's chat transcript."""
        session_dir = os.path.join(self._data_dir, session_id)
        chat_path = os.path.join(session_dir, "chat.json")
        if not os.path.exists(chat_path):
            raise KeyError(f"Session {session_id} not found")

        with open(chat_path) as f:
            chat = json.load(f)
        chat.append(message)
        with open(chat_path, "w") as f:
            json.dump(chat, f)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_persistence.py -v`
Expected: All 19 tests PASS (7 model + 12 persistence)

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/sessions/persistence.py src/backend/tests/unit/test_persistence.py
git commit -m "feat(sessions): add SessionPersistence class with JSON storage [TASK-13]"
```

---

## Task 3: Bundle Metadata Extraction

**Files:**
- Create: `src/backend/app/sessions/metadata.py`
- Test: `src/backend/tests/unit/test_metadata.py` (create)

- [ ] **Step 1: Write tests for metadata extraction**

Create `src/backend/tests/unit/test_metadata.py`:

```python
"""Tests for bundle metadata extraction."""

import json
import pytest
from app.sessions.metadata import extract_bundle_metadata
from app.models.schemas import BundleMetadata


class TestExtractBundleMetadata:
    def test_extracts_k8s_version(self):
        files = {
            "cluster-resources/server-version.json": json.dumps(
                {"major": "1", "minor": "28", "gitVersion": "v1.28.4"}
            ).encode()
        }
        meta = extract_bundle_metadata(files)
        assert meta.k8s_version == "v1.28.4"

    def test_extracts_node_count(self):
        files = {
            "cluster-resources/nodes.json": json.dumps(
                {"items": [{"metadata": {"name": "node1"}}, {"metadata": {"name": "node2"}}]}
            ).encode()
        }
        meta = extract_bundle_metadata(files)
        assert meta.node_count == 2

    def test_extracts_namespaces_from_paths(self):
        files = {
            "cluster-resources/pods/default.json": b"{}",
            "cluster-resources/pods/kube-system.json": b"{}",
            "cluster-resources/pods/app.json": b"{}",
        }
        meta = extract_bundle_metadata(files)
        assert sorted(meta.namespaces) == ["app", "default", "kube-system"]

    def test_extracts_cluster_name(self):
        files = {
            "cluster-info/cluster_version.json": json.dumps(
                {"status": {"desired": {"version": "4.12"}}}
            ).encode(),
        }
        # No direct cluster name in most bundles — returns None
        meta = extract_bundle_metadata(files)
        assert meta.cluster is None  # cluster name extraction is best-effort

    def test_handles_missing_files_gracefully(self):
        meta = extract_bundle_metadata({})
        assert meta.k8s_version is None
        assert meta.node_count is None
        assert meta.namespaces == []

    def test_handles_malformed_json(self):
        files = {
            "cluster-resources/server-version.json": b"not json",
            "cluster-resources/nodes.json": b"{invalid",
        }
        meta = extract_bundle_metadata(files)
        assert meta.k8s_version is None
        assert meta.node_count is None

    def test_returns_bundle_metadata_type(self):
        meta = extract_bundle_metadata({})
        assert isinstance(meta, BundleMetadata)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_metadata.py -v`
Expected: ImportError

- [ ] **Step 3: Implement extract_bundle_metadata**

Create `src/backend/app/sessions/metadata.py`:

```python
"""Extract structured metadata from support bundle files."""

import json
import logging
import os
import re

from app.models.schemas import BundleMetadata

logger = logging.getLogger(__name__)

# Pattern to match namespace-scoped resource files like:
# cluster-resources/pods/default.json
# cluster-resources/deployments/kube-system.json
_NAMESPACE_PATTERN = re.compile(
    r"cluster-resources/[^/]+/([a-z0-9][-a-z0-9]*)\.json$"
)


def extract_bundle_metadata(
    extracted_files: dict[str, bytes],
) -> BundleMetadata:
    """Extract cluster metadata from bundle files.

    Best-effort extraction — returns defaults for anything missing or
    malformed. Never raises on bad data.
    """
    k8s_version = _extract_k8s_version(extracted_files)
    node_count = _extract_node_count(extracted_files)
    namespaces = _extract_namespaces(extracted_files)

    return BundleMetadata(
        cluster=None,  # No reliable source in standard bundles
        k8s_version=k8s_version,
        node_count=node_count,
        namespaces=sorted(namespaces),
    )


def _extract_k8s_version(files: dict[str, bytes]) -> str | None:
    for path, content in files.items():
        if path.endswith("server-version.json"):
            try:
                data = json.loads(content)
                return data.get("gitVersion")
            except (json.JSONDecodeError, AttributeError):
                return None
    return None


def _extract_node_count(files: dict[str, bytes]) -> int | None:
    for path, content in files.items():
        if path.endswith("nodes.json") and "cluster-resources" in path:
            try:
                data = json.loads(content)
                items = data.get("items", [])
                return len(items)
            except (json.JSONDecodeError, AttributeError):
                return None
    return None


def _extract_namespaces(files: dict[str, bytes]) -> list[str]:
    namespaces: set[str] = set()
    for path in files:
        match = _NAMESPACE_PATTERN.search(path)
        if match:
            ns = match.group(1)
            # Filter out non-namespace filenames
            if ns not in ("cluster", "node", "global"):
                namespaces.add(ns)
    return list(namespaces)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_metadata.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/sessions/metadata.py src/backend/tests/unit/test_metadata.py
git commit -m "feat(sessions): add bundle metadata extraction [TASK-13]"
```

---

## Task 4: Session API Routes

**Files:**
- Create: `src/backend/app/api/session_routes.py`
- Modify: `src/backend/app/main.py` (register routes)
- Test: `src/backend/tests/unit/test_session_routes.py` (create)

- [ ] **Step 1: Write tests for session API routes**

Create `src/backend/tests/unit/test_session_routes.py`:

```python
"""Tests for session history API routes."""

import json
import os
import tempfile
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.api.session_routes import get_persistence
from app.sessions.persistence import SessionPersistence
from app.models.schemas import SessionSummary, FindingSummary, BundleMetadata


@pytest.fixture
def tmp_persistence():
    tmpdir = tempfile.mkdtemp()
    store = SessionPersistence(data_dir=tmpdir)
    return store


@pytest.fixture
def client(tmp_persistence):
    app.dependency_overrides[get_persistence] = lambda: tmp_persistence
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_summary(sid="s1"):
    return SessionSummary(
        id=sid,
        bundle_name="test.tar.gz",
        file_size=1024,
        timestamp="2026-03-21T12:00:00Z",
        status="completed",
        bundle_metadata=BundleMetadata(cluster="prod"),
        findings_summary=[FindingSummary(severity="critical", title="OOM")],
    )


class TestListSessions:
    def test_empty_list(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_saved_sessions(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary("s1"))
        tmp_persistence.save_session(_make_summary("s2"))
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetSession:
    def test_returns_full_session(self, client, tmp_persistence):
        tmp_persistence.save_session(
            _make_summary(), report={"summary": "test"}
        )
        resp = client.get("/api/sessions/s1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["id"] == "s1"
        assert data["report"]["summary"] == "test"

    def test_not_found(self, client):
        resp = client.get("/api/sessions/nonexistent")
        assert resp.status_code == 404


class TestUpdateSession:
    def test_update_notes(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary())
        resp = client.patch(
            "/api/sessions/s1", json={"notes": "Customer ACME"}
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Customer ACME"

    def test_update_tags(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary())
        resp = client.patch(
            "/api/sessions/s1", json={"tags": ["urgent"]}
        )
        assert resp.status_code == 200
        assert resp.json()["tags"] == ["urgent"]

    def test_not_found(self, client):
        resp = client.patch(
            "/api/sessions/nope", json={"notes": "x"}
        )
        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete_existing(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary())
        resp = client.delete("/api/sessions/s1")
        assert resp.status_code == 204

        resp = client.get("/api/sessions")
        assert resp.json() == []

    def test_delete_not_found(self, client):
        resp = client.delete("/api/sessions/nope")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/backend && python -m pytest tests/unit/test_session_routes.py -v`
Expected: ImportError — `session_routes` doesn't exist

- [ ] **Step 3: Implement session API routes**

Create `src/backend/app/api/session_routes.py`:

```python
"""API routes for session history — browse, update, delete past analyses."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.sessions.persistence import SessionPersistence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Singleton — overridable via FastAPI dependency injection for testing
_persistence: SessionPersistence | None = None


def get_persistence() -> SessionPersistence:
    global _persistence
    if _persistence is None:
        _persistence = SessionPersistence()
    return _persistence


class SessionUpdateRequest(BaseModel):
    notes: str | None = None
    tags: list[str] | None = None


@router.get("")
def list_sessions(store: SessionPersistence = Depends(get_persistence)):
    sessions = store.list_sessions()
    return [s.model_dump() for s in sessions]


@router.get("/{session_id}")
def get_session(
    session_id: str, store: SessionPersistence = Depends(get_persistence)
):
    try:
        data = store.get_session(session_id)
        return {
            "summary": data["summary"].model_dump(),
            "report": data["report"],
            "chat": data["chat"],
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.patch("/{session_id}")
def update_session(
    session_id: str,
    body: SessionUpdateRequest,
    store: SessionPersistence = Depends(get_persistence),
):
    try:
        updated = store.update_session(
            session_id, notes=body.notes, tags=body.tags
        )
        return updated.model_dump()
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: str, store: SessionPersistence = Depends(get_persistence)
):
    try:
        store.delete_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
```

- [ ] **Step 4: Register routes in main.py**

In `src/backend/app/main.py`, add after the existing router inclusion (around line 25):

```python
from app.api.session_routes import router as session_router

app.include_router(session_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd src/backend && python -m pytest tests/unit/test_session_routes.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/api/session_routes.py src/backend/tests/unit/test_session_routes.py src/backend/app/main.py
git commit -m "feat(api): add session history CRUD endpoints [TASK-13]"
```

---

## Task 5: Pipeline Integration — Auto-Save on Analysis Completion

**Files:**
- Modify: `src/backend/app/api/routes.py`

This task hooks `SessionPersistence` into the existing analysis and chat endpoints. No new tests file — the integration is verified by an end-to-end test in Task 8.

- [ ] **Step 1: Add imports to routes.py**

At the top of `src/backend/app/api/routes.py`, add:

```python
from app.sessions.persistence import SessionPersistence
from app.sessions.metadata import extract_bundle_metadata
from app.models.schemas import SessionSummary, FindingSummary, LLMMetaSummary
from datetime import datetime, UTC
```

Add a module-level singleton (after `session_store` import, around line 27):

```python
from app.api.session_routes import get_persistence as _get_persistence
```

- [ ] **Step 2: Hook save_session into the analyze endpoint**

In `src/backend/app/api/routes.py`, inside the `analyze()` function, after the report is finalized and the "done" event is yielded (around lines 300-310), add session persistence:

```python
        # --- Session persistence: save completed analysis ---
        try:
            persistence = _get_persistence()
            bundle_metadata = extract_bundle_metadata(session.extracted_files)
            findings = [
                FindingSummary(severity=f.severity, title=f.title)
                for f in report_obj.findings
            ] if report_obj else []

            llm_meta_summary = None
            if provider:
                llm_meta_summary = LLMMetaSummary(
                    provider=provider.provider_name,
                    model=provider.model_name,
                    input_tokens=provider.last_input_tokens,
                    output_tokens=provider.last_output_tokens,
                    latency_ms=tracker.latency_ms if tracker else 0,
                )

            summary = SessionSummary(
                id=session_id,
                bundle_name=session.bundle_manifest.files[0].path.split("/")[0]
                if session.bundle_manifest.files
                else "unknown.tar.gz",
                file_size=session.bundle_manifest.total_size_bytes,
                timestamp=datetime.now(UTC).isoformat(),
                status="completed",
                bundle_metadata=bundle_metadata,
                findings_summary=findings,
                llm_meta=llm_meta_summary,
                eval_score=eval_report.composite_score if eval_report else None,
            )

            report_dict = report_obj.model_dump() if report_obj else {}
            persistence.save_session(summary, report=report_dict)
            logger.info("Session %s persisted to disk", session_id)
        except Exception:
            logger.exception("Failed to persist session %s", session_id)
```

Note: The exact insertion point is after the `yield f"data: {json.dumps(done_event)}\n\n"` line. The `try/except` ensures persistence failures don't break the analysis stream. The `bundle_name` extraction uses the first file's root directory — check existing upload logic to see if the original filename is available on the session or manifest. If the original upload filename is available (e.g., from the multipart form), use that instead. Otherwise, fall back to a heuristic.

- [ ] **Step 3: Hook error persistence**

In the same `analyze()` function, in the `except` blocks where errors are yielded (around lines 260-275), add error session persistence:

```python
            # Persist error session
            try:
                persistence = _get_persistence()
                bundle_metadata = extract_bundle_metadata(session.extracted_files)
                summary = SessionSummary(
                    id=session_id,
                    bundle_name=session.bundle_manifest.files[0].path.split("/")[0]
                    if session.bundle_manifest.files
                    else "unknown.tar.gz",
                    file_size=session.bundle_manifest.total_size_bytes,
                    timestamp=datetime.now(UTC).isoformat(),
                    status="error",
                    bundle_metadata=bundle_metadata,
                )
                persistence.save_session(summary)
            except Exception:
                logger.exception("Failed to persist error session %s", session_id)
```

- [ ] **Step 4: Hook chat message persistence**

In the `chat()` function (around line 334 where `session.chat_history.append` is called), add after the user message append:

```python
        # Persist chat message
        try:
            persistence = _get_persistence()
            persistence.append_chat(session_id, {"role": "user", "content": message, "timestamp": datetime.now(UTC).isoformat()})
        except Exception:
            logger.debug("Chat persistence not available for session %s", session_id)
```

Similarly, after the assistant message is appended (around line 370 in the "done" event handling), add:

```python
            try:
                persistence = _get_persistence()
                persistence.append_chat(session_id, {"role": "assistant", "content": full_response, "timestamp": datetime.now(UTC).isoformat()})
            except Exception:
                logger.debug("Chat persistence not available for session %s", session_id)
```

- [ ] **Step 5: Run existing tests to verify nothing breaks**

Run: `cd src/backend && python -m pytest -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/api/routes.py
git commit -m "feat(pipeline): persist sessions on analysis completion and chat [TASK-13]"
```

---

## Task 6: Docker Volume Configuration

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add named volume to docker-compose.yml**

Add a `volumes` section to the `backend` service and a top-level `volumes` declaration. Under the `backend` service:

```yaml
    volumes:
      - session-data:/app/data/sessions
```

At the top level (after `services:`):

```yaml
volumes:
  session-data:
```

- [ ] **Step 2: Verify docker compose config is valid**

Run: `docker compose config --quiet`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add session-data Docker volume for persistence [TASK-13]"
```

---

## Task 7: Frontend Types

**Files:**
- Modify: `src/frontend/src/types/api.ts`

- [ ] **Step 1: Add session explorer TypeScript types**

Append to `src/frontend/src/types/api.ts`:

```typescript
/* ── Session Explorer types ────────────────────────── */

export interface FindingSummary {
  severity: 'critical' | 'warning' | 'info'
  title: string
}

export interface BundleMetadataSummary {
  cluster: string | null
  namespaces: string[]
  k8s_version: string | null
  node_count: number | null
}

export interface LLMMetaSummary {
  provider: string
  model: string
  input_tokens: number
  output_tokens: number
  latency_ms: number
}

export interface SessionSummary {
  id: string
  bundle_name: string
  file_size: number
  timestamp: string
  status: 'completed' | 'error'
  bundle_metadata: BundleMetadataSummary
  findings_summary: FindingSummary[]
  llm_meta: LLMMetaSummary | null
  eval_score: number | null
  notes: string
  tags: string[]
}

export interface SessionDetail {
  summary: SessionSummary
  report: DiagnosticReport | null
  chat: ChatMessage[]
}
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/types/api.ts
git commit -m "feat(frontend): add session explorer TypeScript types [TASK-13]"
```

---

## Task 8: SessionExplorer Component (Dashboard Table)

**Files:**
- Create: `src/frontend/src/components/SessionExplorer.tsx`

- [ ] **Step 1: Implement SessionExplorer component**

Create `src/frontend/src/components/SessionExplorer.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { SessionSummary } from '../types/api'

interface SessionExplorerProps {
  onNewAnalysis: () => void
  onSelectSession: (sessionId: string) => void
}

function formatRelativeTime(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function SessionExplorer({ onNewAnalysis, onSelectSession }: SessionExplorerProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'error'>('all')
  const [severityFilter, setSeverityFilter] = useState<'all' | 'critical'>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const fetchSessions = useCallback(async () => {
    try {
      setLoading(true)
      const resp = await fetch('/api/sessions')
      if (!resp.ok) throw new Error('Failed to load sessions')
      const data = await resp.json()
      setSessions(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  const filtered = useMemo(() => {
    return sessions.filter(s => {
      if (statusFilter !== 'all' && s.status !== statusFilter) return false
      if (severityFilter === 'critical' && !s.findings_summary.some(f => f.severity === 'critical')) return false
      if (search) {
        const q = search.toLowerCase()
        const matchesName = s.bundle_name.toLowerCase().includes(q)
        const matchesCluster = s.bundle_metadata?.cluster?.toLowerCase().includes(q)
        const matchesNotes = s.notes?.toLowerCase().includes(q)
        if (!matchesName && !matchesCluster && !matchesNotes) return false
      }
      return true
    })
  }, [sessions, statusFilter, severityFilter, search])

  const stats = useMemo(() => ({
    total: sessions.length,
    withCritical: sessions.filter(s => s.findings_summary.some(f => f.severity === 'critical')).length,
    completed: sessions.filter(s => s.status === 'completed').length,
    errored: sessions.filter(s => s.status === 'error').length,
  }), [sessions])

  const handleRowClick = (session: SessionSummary) => {
    setSelectedId(session.id)
    onSelectSession(session.id)
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300">
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-zinc-100">Unravel</h1>
            <p className="text-sm text-zinc-500 mt-1">Support Bundle Analysis</p>
          </div>
          <button
            onClick={onNewAnalysis}
            className="px-4 py-2 bg-teal-400 text-zinc-950 rounded-lg text-sm font-semibold hover:bg-teal-300 transition-colors"
          >
            + New Analysis
          </button>
        </div>

        {/* Stats bar */}
        {sessions.length > 0 && (
          <div className="grid grid-cols-4 gap-4 mb-6 p-4 bg-zinc-900 rounded-lg border border-zinc-800">
            <div className="text-center">
              <div className="text-2xl font-bold text-zinc-100">{stats.total}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">Total Sessions</div>
            </div>
            <div className="text-center border-l border-zinc-800">
              <div className="text-2xl font-bold text-red-500">{stats.withCritical}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">With Critical</div>
            </div>
            <div className="text-center border-l border-zinc-800">
              <div className="text-2xl font-bold text-teal-400">{stats.completed}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">Completed</div>
            </div>
            <div className="text-center border-l border-zinc-800">
              <div className="text-2xl font-bold text-red-500">{stats.errored}</div>
              <div className="text-[10px] uppercase tracking-widest text-zinc-500">Errored</div>
            </div>
          </div>
        )}

        {/* Filter bar */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="🔍 Search by bundle name, cluster, notes..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-zinc-600"
          />
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as 'all' | 'completed' | 'error')}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-400"
          >
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="error">Errored</option>
          </select>
          <select
            value={severityFilter}
            onChange={e => setSeverityFilter(e.target.value as 'all' | 'critical')}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm text-zinc-400"
          >
            <option value="all">All Severities</option>
            <option value="critical">Has Critical</option>
          </select>
        </div>

        {/* Table */}
        {loading ? (
          <div className="text-center py-16 text-zinc-500">Loading sessions...</div>
        ) : error ? (
          <div className="text-center py-16 text-red-400">{error}</div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-zinc-500 mb-4">No analyses yet</p>
            <button
              onClick={onNewAnalysis}
              className="px-6 py-3 bg-teal-400 text-zinc-950 rounded-lg font-semibold hover:bg-teal-300 transition-colors"
            >
              Analyze Your First Bundle
            </button>
          </div>
        ) : (
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[2.5fr_1fr_1.2fr_0.8fr_80px] gap-2 px-4 py-2 text-[10px] uppercase tracking-widest text-zinc-500 border-b border-zinc-800">
              <span>Bundle</span>
              <span>Cluster</span>
              <span>Findings</span>
              <span>Analyzed</span>
              <span>Status</span>
            </div>

            {/* Rows */}
            {filtered.map(session => {
              const critCount = session.findings_summary.filter(f => f.severity === 'critical').length
              const warnCount = session.findings_summary.filter(f => f.severity === 'warning').length
              const infoCount = session.findings_summary.filter(f => f.severity === 'info').length

              return (
                <div
                  key={session.id}
                  onClick={() => handleRowClick(session)}
                  className={`grid grid-cols-[2.5fr_1fr_1.2fr_0.8fr_80px] gap-2 px-4 py-3 border-b border-zinc-800/50 cursor-pointer hover:bg-zinc-800/30 transition-colors ${
                    selectedId === session.id ? 'bg-teal-400/5 border-l-2 border-l-teal-400' : ''
                  } ${session.status === 'error' ? 'opacity-50' : ''}`}
                >
                  <div>
                    <div className="text-zinc-100 font-mono text-sm truncate">{session.bundle_name}</div>
                    {session.notes && (
                      <div className="text-zinc-500 text-xs mt-0.5 truncate">{session.notes}</div>
                    )}
                  </div>
                  <span className="text-zinc-400 font-mono text-sm self-center">
                    {session.bundle_metadata?.cluster || '—'}
                  </span>
                  <div className="self-center text-sm">
                    {session.status === 'error' ? (
                      <span className="text-zinc-500">—</span>
                    ) : (
                      <>
                        {critCount > 0 && <span className="text-red-500">{critCount} crit</span>}
                        {critCount > 0 && (warnCount > 0 || infoCount > 0) && <span className="text-zinc-600"> · </span>}
                        {warnCount > 0 && <span className="text-amber-500">{warnCount} warn</span>}
                        {warnCount > 0 && infoCount > 0 && <span className="text-zinc-600"> · </span>}
                        {infoCount > 0 && <span className="text-blue-400">{infoCount} info</span>}
                        {critCount === 0 && warnCount === 0 && infoCount === 0 && <span className="text-zinc-500">—</span>}
                      </>
                    )}
                  </div>
                  <span className="text-zinc-400 text-sm self-center">
                    {formatRelativeTime(session.timestamp)}
                  </span>
                  <span className={`text-sm self-center ${session.status === 'completed' ? 'text-teal-400' : 'text-red-500'}`}>
                    ● {session.status === 'completed' ? 'Done' : 'Error'}
                  </span>
                </div>
              )
            })}

            {filtered.length === 0 && sessions.length > 0 && (
              <div className="text-center py-8 text-zinc-500">No sessions match your filters</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd src/frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/SessionExplorer.tsx
git commit -m "feat(frontend): add SessionExplorer dashboard component [TASK-13]"
```

---

## Task 9: SessionDetail Panel

**Files:**
- Create: `src/frontend/src/components/SessionDetail.tsx`

- [ ] **Step 1: Implement SessionDetail panel**

Create `src/frontend/src/components/SessionDetail.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import type { SessionDetail as SessionDetailType } from '../types/api'

interface SessionDetailProps {
  sessionId: string
  onClose: () => void
  onOpenReport: (detail: SessionDetailType) => void
  onDelete: (sessionId: string) => void
}

export function SessionDetail({ sessionId, onClose, onOpenReport, onDelete }: SessionDetailProps) {
  const [detail, setDetail] = useState<SessionDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [showObservability, setShowObservability] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(`/api/sessions/${sessionId}`)
      .then(r => r.json())
      .then(data => {
        if (!cancelled) {
          setDetail(data)
          setNotes(data.summary.notes || '')
          setLoading(false)
        }
      })
      .catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [sessionId])

  const handleSaveNotes = useCallback(async () => {
    setSaving(true)
    try {
      await fetch(`/api/sessions/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes }),
      })
    } finally {
      setSaving(false)
    }
  }, [sessionId, notes])

  const handleDelete = useCallback(async () => {
    if (!confirm('Delete this session? This cannot be undone.')) return
    await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
    onDelete(sessionId)
  }, [sessionId, onDelete])

  if (loading) {
    return (
      <div className="w-[340px] bg-zinc-900 border-l border-zinc-800 p-4 flex items-center justify-center">
        <span className="text-zinc-500 text-sm">Loading...</span>
      </div>
    )
  }

  if (!detail) return null

  const { summary } = detail
  const meta = summary.bundle_metadata

  return (
    <div className="w-[340px] bg-zinc-900 border-l border-zinc-800 p-4 overflow-y-auto flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1 min-w-0">
          <div className="text-zinc-100 font-mono text-sm font-semibold truncate">
            {summary.bundle_name}
          </div>
          <div className="text-zinc-500 text-[10px] mt-1">
            Analyzed {new Date(summary.timestamp).toLocaleString()} · {(summary.file_size / 1024 / 1024).toFixed(1)} MB
          </div>
        </div>
        <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 ml-2 text-lg">✕</button>
      </div>

      {/* Notes */}
      <div className="mb-4">
        <div className="text-zinc-500 text-[9px] uppercase tracking-widest mb-1">Notes</div>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          onBlur={handleSaveNotes}
          placeholder="Add context: customer, ticket number, cluster..."
          className="w-full bg-zinc-950 border border-zinc-800 rounded-md p-2 text-xs text-zinc-300 placeholder-zinc-600 resize-none focus:outline-none focus:border-zinc-600"
          rows={3}
        />
        {saving && <div className="text-[9px] text-zinc-500 mt-1">Saving...</div>}
      </div>

      {/* Bundle metadata */}
      {meta && (meta.cluster || meta.k8s_version || meta.node_count || meta.namespaces.length > 0) && (
        <div className="mb-4">
          <div className="text-zinc-500 text-[9px] uppercase tracking-widest mb-2">Bundle Metadata</div>
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            {meta.cluster && <>
              <span className="text-zinc-500">Cluster</span>
              <span className="text-zinc-300 font-mono">{meta.cluster}</span>
            </>}
            {meta.node_count != null && <>
              <span className="text-zinc-500">Nodes</span>
              <span className="text-zinc-300">{meta.node_count}</span>
            </>}
            {meta.namespaces.length > 0 && <>
              <span className="text-zinc-500">Namespaces</span>
              <span className="text-zinc-300 font-mono">{meta.namespaces.join(', ')}</span>
            </>}
            {meta.k8s_version && <>
              <span className="text-zinc-500">K8s Version</span>
              <span className="text-zinc-300 font-mono">{meta.k8s_version}</span>
            </>}
          </div>
        </div>
      )}

      {/* Findings */}
      {summary.findings_summary.length > 0 && (
        <div className="mb-4">
          <div className="text-zinc-500 text-[9px] uppercase tracking-widest mb-2">Findings</div>
          <div className="space-y-1">
            {summary.findings_summary.map((f, i) => (
              <div key={i} className="flex items-start gap-2 py-1 border-b border-zinc-800/50 last:border-0">
                <span className={`text-[8px] mt-1 ${
                  f.severity === 'critical' ? 'text-red-500' :
                  f.severity === 'warning' ? 'text-amber-500' : 'text-blue-400'
                }`}>●</span>
                <span className="text-zinc-300 text-xs">{f.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 mt-auto pt-4">
        <button
          onClick={() => onOpenReport(detail)}
          className="flex-1 px-3 py-2 bg-teal-400 text-zinc-950 rounded-lg text-sm font-semibold hover:bg-teal-300 transition-colors text-center"
        >
          Open Full Report
        </button>
        <button
          onClick={handleDelete}
          className="px-3 py-2 bg-zinc-800 text-zinc-500 border border-zinc-700 rounded-lg text-sm hover:text-zinc-300 transition-colors"
        >
          🗑
        </button>
      </div>

      {/* LLM Observability (collapsible) */}
      {summary.llm_meta && (
        <div className="mt-4 pt-3 border-t border-zinc-800">
          <button
            onClick={() => setShowObservability(!showObservability)}
            className="text-zinc-500 text-[9px] uppercase tracking-widest hover:text-zinc-400"
          >
            {showObservability ? '▾' : '▸'} LLM Observability
          </button>
          {showObservability && (
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs mt-2">
              <span className="text-zinc-500">Provider</span>
              <span className="text-zinc-300">{summary.llm_meta.provider}</span>
              <span className="text-zinc-500">Model</span>
              <span className="text-zinc-300 font-mono">{summary.llm_meta.model}</span>
              <span className="text-zinc-500">Tokens</span>
              <span className="text-zinc-300">
                {summary.llm_meta.input_tokens.toLocaleString()} in / {summary.llm_meta.output_tokens.toLocaleString()} out
              </span>
              <span className="text-zinc-500">Latency</span>
              <span className="text-zinc-300">{(summary.llm_meta.latency_ms / 1000).toFixed(1)}s</span>
              {summary.eval_score != null && <>
                <span className="text-zinc-500">Eval Score</span>
                <span className="text-zinc-300">{(summary.eval_score * 100).toFixed(0)}%</span>
              </>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd src/frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/components/SessionDetail.tsx
git commit -m "feat(frontend): add SessionDetail slide-out panel [TASK-13]"
```

---

## Task 10: App Navigation — Wire Explorer Into App.tsx

**Files:**
- Modify: `src/frontend/src/App.tsx`

- [ ] **Step 1: Update AppPhase type and initial state**

In `src/frontend/src/App.tsx`:

Change line 13:
```typescript
type AppPhase = 'explorer' | 'upload' | 'dashboard'
```

Change line 16:
```typescript
const [phase, setPhase] = useState<AppPhase>('explorer')
```

Add new state for the detail panel (after the existing state declarations around line 24):
```typescript
const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
```

Add imports at the top:
```typescript
import { SessionExplorer } from './components/SessionExplorer'
import { SessionDetail } from './components/SessionDetail'
import type { SessionDetail as SessionDetailType } from './types/api'
```

- [ ] **Step 2: Add handler for opening saved sessions**

Add a new handler after `handleReset` (around line 55):

```typescript
const handleOpenSavedSession = useCallback((detail: SessionDetailType) => {
  // Load saved session data into the same state variables the existing
  // ReportPhase and ChatPhase use, then switch to dashboard phase
  setSessionId(detail.summary.id)
  setReport(detail.report)
  setChatMessages(detail.chat || [])
  // Create a minimal manifest from the summary for ReportPhase props
  setManifest({
    total_files: 0,
    total_size_bytes: detail.summary.file_size,
    files: [],
  })
  setSignalSummary({})
  setSelectedSessionId(null)
  setPhase('dashboard')
}, [])

const handleBackToExplorer = useCallback(() => {
  setReport(null)
  setSelectedFile(null)
  setChatMessages([])
  setSessionId(null)
  setManifest(null)
  setSignalSummary({})
  setSelectedSessionId(null)
  setPhase('explorer')
}, [])

const handleSessionDeleted = useCallback((deletedId: string) => {
  setSelectedSessionId(null)
}, [])
```

- [ ] **Step 3: Update the render to include explorer phase**

In the JSX return, add the explorer phase before the existing upload phase. The structure should be:

```tsx
{phase === 'explorer' && (
  <div className="flex h-screen">
    <div className="flex-1 overflow-auto">
      <SessionExplorer
        onNewAnalysis={() => setPhase('upload')}
        onSelectSession={(id) => setSelectedSessionId(id)}
      />
    </div>
    {selectedSessionId && (
      <SessionDetail
        sessionId={selectedSessionId}
        onClose={() => setSelectedSessionId(null)}
        onOpenReport={handleOpenSavedSession}
        onDelete={handleSessionDeleted}
      />
    )}
  </div>
)}
```

- [ ] **Step 4: Add "Back to Explorer" to the dashboard phase header**

In the dashboard phase's header area (where the logo and reset button are), replace the reset/back-to-upload behavior with a "Back to Explorer" button:

```tsx
<button
  onClick={handleBackToExplorer}
  className="text-zinc-500 hover:text-zinc-300 text-sm transition-colors"
>
  ← Back to Explorer
</button>
```

- [ ] **Step 5: Update handleReset to return to explorer instead of upload**

Change `handleReset` to navigate to `'explorer'` instead of `'upload'`:

```typescript
setPhase('explorer')
```

- [ ] **Step 6: Verify it compiles and renders**

Run: `cd src/frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 7: Commit**

```bash
git add src/frontend/src/App.tsx
git commit -m "feat(frontend): wire session explorer as landing page [TASK-13]"
```

---

## Task 11: Integration Test — End-to-End Session Persistence

**Files:**
- Create: `src/backend/tests/integration/test_session_persistence.py`

- [ ] **Step 1: Write integration test**

Create `src/backend/tests/integration/test_session_persistence.py`:

```python
"""Integration test: verify analysis completion persists a session."""

import json
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.api.session_routes import get_persistence
from app.sessions.persistence import SessionPersistence


@pytest.fixture
def tmp_persistence():
    tmpdir = tempfile.mkdtemp()
    store = SessionPersistence(data_dir=tmpdir)
    return store


@pytest.fixture
def client(tmp_persistence):
    app.dependency_overrides[get_persistence] = lambda: tmp_persistence
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestSessionPersistenceIntegration:
    def test_list_then_detail_roundtrip(self, client, tmp_persistence):
        """Verify the API can list and retrieve sessions saved by persistence."""
        from app.models.schemas import SessionSummary, FindingSummary, BundleMetadata

        summary = SessionSummary(
            id="integration-test-1",
            bundle_name="integration.tar.gz",
            file_size=2048,
            timestamp="2026-03-21T12:00:00Z",
            status="completed",
            bundle_metadata=BundleMetadata(
                cluster="test-cluster",
                namespaces=["default"],
                k8s_version="v1.28.4",
                node_count=2,
            ),
            findings_summary=[
                FindingSummary(severity="critical", title="Pod CrashLoop"),
                FindingSummary(severity="warning", title="No resource limits"),
            ],
        )
        report = {
            "executive_summary": "Integration test report",
            "findings": [],
        }
        tmp_persistence.save_session(summary, report=report)

        # List
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["id"] == "integration-test-1"
        assert sessions[0]["bundle_metadata"]["cluster"] == "test-cluster"

        # Detail
        resp = client.get("/api/sessions/integration-test-1")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["report"]["executive_summary"] == "Integration test report"
        assert detail["chat"] == []

    def test_update_notes_and_verify(self, client, tmp_persistence):
        from app.models.schemas import SessionSummary
        tmp_persistence.save_session(SessionSummary(
            id="note-test",
            bundle_name="test.tar.gz",
            file_size=512,
            timestamp="2026-03-21T12:00:00Z",
            status="completed",
        ))

        # Update notes
        resp = client.patch("/api/sessions/note-test", json={"notes": "ACME Corp - TICKET-123"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "ACME Corp - TICKET-123"

        # Verify persisted
        resp = client.get("/api/sessions")
        assert resp.json()[0]["notes"] == "ACME Corp - TICKET-123"

    def test_delete_removes_from_list(self, client, tmp_persistence):
        from app.models.schemas import SessionSummary
        tmp_persistence.save_session(SessionSummary(
            id="delete-test",
            bundle_name="test.tar.gz",
            file_size=512,
            timestamp="2026-03-21T12:00:00Z",
            status="completed",
        ))

        resp = client.delete("/api/sessions/delete-test")
        assert resp.status_code == 204

        resp = client.get("/api/sessions")
        assert resp.json() == []
```

- [ ] **Step 2: Run integration tests**

Run: `cd src/backend && python -m pytest tests/integration/test_session_persistence.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Run full test suite to verify nothing is broken**

Run: `cd src/backend && python -m pytest -v`
Expected: All tests PASS (existing 127+ tests + new tests)

- [ ] **Step 4: Commit**

```bash
git add src/backend/tests/integration/test_session_persistence.py
git commit -m "test: add integration tests for session persistence [TASK-13]"
```

---

## Task Dependency Graph

```
Task 1 (Models)
  ↓
Task 2 (SessionPersistence) ──→ Task 5 (Pipeline Integration)
  ↓                                ↓
Task 3 (Metadata Extraction)    Task 6 (Docker Volume)
  ↓
Task 4 (API Routes) ──────────→ Task 11 (Integration Tests)
  ↓
Task 7 (Frontend Types)
  ↓
Task 8 (SessionExplorer) ─────→ Task 10 (App Navigation)
  ↓
Task 9 (SessionDetail) ───────→ Task 10 (App Navigation)
```

**Parallelizable groups:**
- Task 1 first (models — required by Tasks 2, 3, 4)
- Tasks 2 + 3 can run in parallel after Task 1
- Tasks 8 + 9 can run in parallel after Task 7
- Task 10 depends on 8 + 9
- Task 11 depends on 4 + 5
