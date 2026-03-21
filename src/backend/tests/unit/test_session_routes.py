"""Tests for session history API routes."""

import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.session_routes import get_persistence
from app.sessions.persistence import SessionPersistence
from app.models.schemas import SessionSummary, FindingSummary, BundleMetadata


@pytest.fixture
def tmp_persistence():
    tmpdir = tempfile.mkdtemp()
    return SessionPersistence(data_dir=tmpdir)


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
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_saved_sessions(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary("s1"))
        tmp_persistence.save_session(_make_summary("s2"))
        resp = client.get("/api/history")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


class TestGetSession:
    def test_returns_full_session(self, client, tmp_persistence):
        tmp_persistence.save_session(
            _make_summary(), report={"summary": "test"}
        )
        resp = client.get("/api/history/s1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["id"] == "s1"
        assert data["report"]["summary"] == "test"

    def test_not_found(self, client):
        resp = client.get("/api/history/nonexistent")
        assert resp.status_code == 404


class TestUpdateSession:
    def test_update_notes(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary())
        resp = client.patch(
            "/api/history/s1", json={"notes": "Customer ACME"}
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Customer ACME"

    def test_update_tags(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary())
        resp = client.patch(
            "/api/history/s1", json={"tags": ["urgent"]}
        )
        assert resp.status_code == 200
        assert resp.json()["tags"] == ["urgent"]

    def test_not_found(self, client):
        resp = client.patch(
            "/api/history/nope", json={"notes": "x"}
        )
        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete_existing(self, client, tmp_persistence):
        tmp_persistence.save_session(_make_summary())
        resp = client.delete("/api/history/s1")
        assert resp.status_code == 204

        resp = client.get("/api/history")
        assert resp.json() == []

    def test_delete_not_found(self, client):
        resp = client.delete("/api/history/nope")
        assert resp.status_code == 404
