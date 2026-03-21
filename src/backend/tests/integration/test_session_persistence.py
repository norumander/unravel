"""Integration test: verify session persistence through the API layer."""

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


class TestSessionPersistenceIntegration:
    def test_list_then_detail_roundtrip(self, client, tmp_persistence):
        """Verify the API can list and retrieve sessions saved by persistence."""
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
        resp = client.get("/api/history")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["id"] == "integration-test-1"
        assert sessions[0]["bundle_metadata"]["cluster"] == "test-cluster"

        # Detail
        resp = client.get("/api/history/integration-test-1")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["report"]["executive_summary"] == "Integration test report"
        assert detail["chat"] == []

    def test_update_notes_and_verify(self, client, tmp_persistence):
        """Verify notes update persists and appears in subsequent list."""
        tmp_persistence.save_session(SessionSummary(
            id="note-test",
            bundle_name="test.tar.gz",
            file_size=512,
            timestamp="2026-03-21T12:00:00Z",
            status="completed",
        ))

        # Update notes
        resp = client.patch("/api/history/note-test", json={"notes": "ACME Corp - TICKET-123"})
        assert resp.status_code == 200
        assert resp.json()["notes"] == "ACME Corp - TICKET-123"

        # Verify persisted
        resp = client.get("/api/history")
        assert resp.json()[0]["notes"] == "ACME Corp - TICKET-123"

    def test_delete_removes_from_list(self, client, tmp_persistence):
        """Verify delete removes session from both list and detail."""
        tmp_persistence.save_session(SessionSummary(
            id="delete-test",
            bundle_name="test.tar.gz",
            file_size=512,
            timestamp="2026-03-21T12:00:00Z",
            status="completed",
        ))

        resp = client.delete("/api/history/delete-test")
        assert resp.status_code == 204

        resp = client.get("/api/history")
        assert resp.json() == []

        resp = client.get("/api/history/delete-test")
        assert resp.status_code == 404
