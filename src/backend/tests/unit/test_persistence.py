"""Tests for session persistence data models and SessionPersistence class."""

import json
import os
import tempfile

import pytest
from datetime import datetime, UTC
from app.models.schemas import (
    FindingSummary,
    BundleMetadata,
    LLMMetaSummary,
    SessionSummary,
)
from app.sessions.persistence import SessionPersistence


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
