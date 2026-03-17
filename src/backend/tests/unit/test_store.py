"""Unit tests for the in-memory session store."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.schemas import BundleFile, BundleManifest, SignalType
from app.sessions.store import MAX_SESSIONS, SESSION_TTL_SECONDS, SessionNotFoundError, SessionStore


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


class TestCapacityEviction:
    def test_create_evicts_oldest_when_at_capacity(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        """S-12: Fill store to MAX_SESSIONS, create one more, verify count is
        still 20 and the oldest session was evicted."""
        now = datetime.now(tz=UTC)
        sessions = []
        for i in range(MAX_SESSIONS):
            s = store.create(sample_manifest, sample_files, sample_classified)
            # Stagger created_at so oldest is deterministic, all within TTL
            s.created_at = now - timedelta(seconds=i)
            sessions.append(s)

        # sessions[0] has the most recent created_at, sessions[-1] is the oldest
        oldest = sessions[-1]
        newest_existing = sessions[0]

        # Create one more — should evict the oldest
        new_session = store.create(sample_manifest, sample_files, sample_classified)

        assert len(store._sessions) == MAX_SESSIONS
        assert oldest.session_id not in store._sessions
        assert newest_existing.session_id in store._sessions
        assert new_session.session_id in store._sessions

    def test_newest_session_always_kept_after_capacity_eviction(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        """Verify the most recently created session is always retained."""
        for i in range(MAX_SESSIONS):
            s = store.create(sample_manifest, sample_files, sample_classified)
            s.created_at = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=i)

        new_session = store.create(sample_manifest, sample_files, sample_classified)
        retrieved = store.get(new_session.session_id)
        assert retrieved.session_id == new_session.session_id


class TestTTLEviction:
    def test_expired_session_evicted_on_get(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        """S-13: Create two sessions, expire one, call get() on the other,
        and verify the expired one is evicted."""
        expired_session = store.create(sample_manifest, sample_files, sample_classified)
        valid_session = store.create(sample_manifest, sample_files, sample_classified)

        # Push expired_session 2 hours into the past
        expired_session.created_at = datetime.now(tz=UTC) - timedelta(hours=2)

        # Accessing the valid session triggers eviction of the expired one
        store.get(valid_session.session_id)
        assert expired_session.session_id not in store._sessions

    def test_session_at_exactly_ttl_boundary_still_valid(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        """S-14: A session whose age is exactly SESSION_TTL_SECONDS should still
        be retrievable because the eviction uses > (not >=)."""
        fixed_now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = store.create(sample_manifest, sample_files, sample_classified)
        session.created_at = fixed_now - timedelta(seconds=SESSION_TTL_SECONDS)

        with patch("app.sessions.store.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            retrieved = store.get(session.session_id)
        assert retrieved.session_id == session.session_id

    def test_session_past_ttl_is_evicted(
        self, store: SessionStore, sample_manifest, sample_files, sample_classified
    ):
        """S-15: A session 3601 seconds old should be evicted and raise
        SessionNotFoundError on get()."""
        fixed_now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        session = store.create(sample_manifest, sample_files, sample_classified)
        session.created_at = fixed_now - timedelta(seconds=SESSION_TTL_SECONDS + 1)

        with patch("app.sessions.store.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            with pytest.raises(SessionNotFoundError):
                store.get(session.session_id)
