"""Integration tests for API endpoints."""

import io
import json
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import reset_provider
from app.main import app
from app.sessions.store import session_store


def _make_tar_gz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def sample_bundle():
    return _make_tar_gz({
        "bundle/logs/pod.log": b"ERROR: OOMKilled\nRestarting container",
        "bundle/cluster-info/version.json": b'{"major":"1","minor":"28"}',
        "bundle/cluster-resources/pods/default.json": b'{"items":[]}',
        "bundle/events.json": b'[{"reason":"OOMKilling"}]',
        "bundle/nodes/worker-1.json": b'{"status":"Ready"}',
    })


@pytest.fixture(autouse=True)
def clear_state():
    """Clear session store and provider cache before each test."""
    session_store._sessions.clear()
    reset_provider()
    yield
    session_store._sessions.clear()
    reset_provider()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestUpload:
    @pytest.mark.asyncio
    async def test_upload_valid_bundle(self, client, sample_bundle):
        response = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "manifest" in data
        assert data["manifest"]["total_files"] == 5

    @pytest.mark.asyncio
    async def test_upload_invalid_file(self, client):
        response = await client.post(
            "/api/upload",
            files={"file": ("readme.txt", b"not a tar.gz", "text/plain")},
        )
        assert response.status_code == 400
        assert "Invalid file format" in response.json()["error"]

    @pytest.mark.asyncio
    async def test_upload_creates_session(self, client, sample_bundle):
        response = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = response.json()["session_id"]
        session = session_store.get(session_id)
        assert session is not None
        assert len(session.extracted_files) == 5

    @pytest.mark.asyncio
    async def test_upload_classifies_signals(self, client, sample_bundle):
        response = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        data = response.json()
        signal_types = {f["signal_type"] for f in data["manifest"]["files"]}
        assert "pod_logs" in signal_types
        assert "events" in signal_types
        assert "cluster_info" in signal_types


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_not_found(self, client):
        response = await client.get("/api/analyze/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analyze_streams_sse(self, client, sample_bundle):
        # Upload first
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_report = json.dumps({
            "executive_summary": "Cluster has OOM issues.",
            "findings": [{
                "severity": "critical",
                "title": "OOMKilled",
                "description": "Pod is being OOM killed",
                "root_cause": "Memory limit too low",
                "remediation": "Increase memory limits",
                "source_signals": ["pod_logs", "events"],
            }],
            "signal_types_analyzed": ["pod_logs", "events", "cluster_info"],
            "truncation_notes": None,
        })

        # Mock the LLM provider
        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 100
        mock_provider.last_output_tokens = 50

        async def mock_analyze(context):
            for chunk in [mock_report[:30], mock_report[30:]]:
                yield chunk

        mock_provider.analyze = mock_analyze

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.get(f"/api/analyze/{session_id}")

        assert response.status_code == 200
        # Parse SSE events from response
        lines = response.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:")]
        assert len(data_lines) >= 2  # At least chunks + report

        # Last event should be the report
        events = [json.loads(l.replace("data: ", "").replace("data:", "")) for l in data_lines]
        report_events = [e for e in events if e.get("type") == "report"]
        assert len(report_events) == 1
        assert report_events[0]["report"]["executive_summary"] == "Cluster has OOM issues."


class TestChat:
    @pytest.mark.asyncio
    async def test_chat_not_found(self, client):
        response = await client.post(
            "/api/chat/nonexistent",
            json={"message": "hello"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_streams_response(self, client, sample_bundle):
        # Upload first
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 100
        mock_provider.last_output_tokens = 50

        async def mock_chat(messages, tools, tool_handler):
            yield "The pod is "
            yield "crash-looping due to OOM."

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.post(
                f"/api/chat/{session_id}",
                json={"message": "What's wrong with the pod?"},
            )

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:")]
        assert len(data_lines) >= 2  # chunks + done

        events = [json.loads(l.replace("data: ", "").replace("data:", "")) for l in data_lines]
        chunk_events = [e for e in events if e.get("type") == "chunk"]
        assert len(chunk_events) >= 1

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_existing_session(self, client, sample_bundle):
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        response = await client.delete(f"/api/sessions/{session_id}")
        assert response.status_code == 200
        assert response.json()["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_session(self, client):
        response = await client.delete("/api/sessions/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_after_delete_session_not_found(self, client, sample_bundle):
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        await client.delete(f"/api/sessions/{session_id}")

        # Analyze should return 404
        response = await client.get(f"/api/analyze/{session_id}")
        assert response.status_code == 404

        # Chat should return 404
        response = await client.post(
            f"/api/chat/{session_id}",
            json={"message": "hello"},
        )
        assert response.status_code == 404
