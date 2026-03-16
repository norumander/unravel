"""Unit tests for the in-memory session store."""

import pytest

from app.models.schemas import BundleFile, BundleManifest, SignalType
from app.sessions.store import SessionNotFoundError, SessionStore


@pytest.fixture
def store() -> SessionStore:
    return SessionStore()


@pytest.fixture
def sample_manifest() -> BundleManifest:
    files = [
        BundleFile(path="logs/pod.log", size_bytes=100, signal_type=SignalType.pod_logs),
    ]
    return BundleManifest(total_files=1, total_size_bytes=100, files=files)


@pytest.fixture
def sample_files() -> dict[str, bytes]:
    return {"logs/pod.log": b"log content"}


@pytest.fixture
def sample_classified() -> dict[SignalType, list[BundleFile]]:
    return {
        SignalType.pod_logs: [
            BundleFile(path="logs/pod.log", size_bytes=100, signal_type=SignalType.pod_logs)
        ],
    }


class TestCreate:
    def test_create_returns_session_with_unique_id(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        session = store.create(sample_manifest, sample_files, sample_classified)
        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_create_returns_sessions_with_different_ids(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        s1 = store.create(sample_manifest, sample_files, sample_classified)
        s2 = store.create(sample_manifest, sample_files, sample_classified)
        assert s1.session_id != s2.session_id

    def test_create_stores_manifest(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        session = store.create(sample_manifest, sample_files, sample_classified)
        assert session.bundle_manifest == sample_manifest

    def test_create_stores_files(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        session = store.create(sample_manifest, sample_files, sample_classified)
        assert session.extracted_files == sample_files

    def test_create_initializes_empty_report_and_chat(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        session = store.create(sample_manifest, sample_files, sample_classified)
        assert session.report is None
        assert session.chat_history == []


class TestGet:
    def test_get_existing_session(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        created = store.create(sample_manifest, sample_files, sample_classified)
        retrieved = store.get(created.session_id)
        assert retrieved.session_id == created.session_id

    def test_get_nonexistent_session_raises_error(self, store: SessionStore):
        with pytest.raises(SessionNotFoundError, match="Session not found"):
            store.get("nonexistent-id")


class TestDelete:
    def test_delete_existing_session(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        session = store.create(sample_manifest, sample_files, sample_classified)
        result = store.delete(session.session_id)
        assert result is True

    def test_delete_removes_session(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        session = store.create(sample_manifest, sample_files, sample_classified)
        store.delete(session.session_id)
        with pytest.raises(SessionNotFoundError):
            store.get(session.session_id)

    def test_delete_nonexistent_session_raises_error(self, store: SessionStore):
        with pytest.raises(SessionNotFoundError, match="Session not found"):
            store.delete("nonexistent-id")

    def test_delete_does_not_affect_other_sessions(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        s1 = store.create(sample_manifest, sample_files, sample_classified)
        s2 = store.create(sample_manifest, sample_files, sample_classified)
        store.delete(s1.session_id)
        retrieved = store.get(s2.session_id)
        assert retrieved.session_id == s2.session_id
