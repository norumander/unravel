"""Integration tests for API endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.provider import TOOL_USE_SENTINEL
from app.models.schemas import ChatMessage, DiagnosticReport
from app.sessions.store import session_store

from .conftest import make_tar_gz


@pytest.fixture
def sample_bundle():
    return make_tar_gz({
        "bundle/logs/pod.log": b"ERROR: OOMKilled\nRestarting container",
        "bundle/cluster-info/version.json": b'{"major":"1","minor":"28"}',
        "bundle/cluster-resources/pods/default.json": b'{"items":[]}',
        "bundle/events.json": b'[{"reason":"OOMKilling"}]',
        "bundle/nodes/worker-1.json": b'{"status":"Ready"}',
    })


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


class TestAnalyzeConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_analyze_returns_409(self, client, sample_bundle):
        """Second analyze request while first is in-flight returns 409."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        # Simulate analysis in progress by setting the flag directly
        session = session_store.get(session_id)
        session.analyzing = True

        response = await client.get(f"/api/analyze/{session_id}")
        assert response.status_code == 409
        assert "already in progress" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_analyzing_flag_reset_after_success(self, client, sample_bundle):
        """The analyzing flag is cleared after successful analysis."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_report = json.dumps({
            "executive_summary": "All good.",
            "findings": [],
            "signal_types_analyzed": ["events"],
            "truncation_notes": None,
        })

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 100
        mock_provider.last_output_tokens = 50

        async def mock_analyze(context):
            yield mock_report

        mock_provider.analyze = mock_analyze

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.get(f"/api/analyze/{session_id}")

        session = session_store.get(session_id)
        assert session.analyzing is False

    @pytest.mark.asyncio
    async def test_analyzing_flag_reset_after_error(self, client, sample_bundle):
        """The analyzing flag is cleared even when analysis fails."""
        from app.llm.provider import LLMError

        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"

        async def mock_analyze_error(context):
            raise LLMError("Rate limit")
            yield  # noqa

        mock_provider.analyze = mock_analyze_error

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.get(f"/api/analyze/{session_id}")

        session = session_store.get(session_id)
        assert session.analyzing is False


class TestAnalyzeMarkdownFences:
    @pytest.mark.asyncio
    async def test_analyze_strips_json_fences(self, client, sample_bundle):
        """LLM response wrapped in ```json fences should still parse."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        raw_json = json.dumps({
            "executive_summary": "Fenced response.",
            "findings": [],
            "signal_types_analyzed": ["events"],
            "truncation_notes": None,
        })
        fenced = f"```json\n{raw_json}\n```"

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 100
        mock_provider.last_output_tokens = 50

        async def mock_analyze(context):
            yield fenced

        mock_provider.analyze = mock_analyze

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.get(f"/api/analyze/{session_id}")

        lines = response.text.strip().split("\n")
        events = [json.loads(l.replace("data: ", "").replace("data:", ""))
                  for l in lines if l.startswith("data:")]
        report_events = [e for e in events if e.get("type") == "report"]
        assert len(report_events) == 1
        assert report_events[0]["report"]["executive_summary"] == "Fenced response."


class TestChatHistoryCap:
    @pytest.mark.asyncio
    async def test_chat_history_capped(self, client, sample_bundle):
        """Chat history should be capped to MAX_CHAT_HISTORY messages."""
        from app.api.routes import MAX_CHAT_HISTORY
        from app.models.schemas import ChatMessage

        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]
        session = session_store.get(session_id)

        # Pre-fill history beyond cap
        for i in range(MAX_CHAT_HISTORY + 10):
            session.chat_history.append(
                ChatMessage(role="user", content=f"message {i}")
            )

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 10
        mock_provider.last_output_tokens = 5

        async def mock_chat(messages, tools, handler):
            yield "ok"

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.post(
                f"/api/chat/{session_id}", json={"message": "one more"}
            )

        # History should be capped (the +1 is for "one more" added before cap)
        assert len(session.chat_history) <= MAX_CHAT_HISTORY + 1  # +1 for assistant reply


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


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """H-1: GET /api/health returns status ok."""
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestChatMessageValidation:
    @pytest.mark.asyncio
    async def test_empty_message_returns_422(self, client, sample_bundle):
        """CH-5: Empty message is rejected by Pydantic validation."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]
        response = await client.post(
            f"/api/chat/{session_id}", json={"message": ""}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_oversized_message_returns_422(self, client, sample_bundle):
        """CH-6: Message over 50,000 chars is rejected."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]
        response = await client.post(
            f"/api/chat/{session_id}", json={"message": "x" * 50_001}
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_single_char_message_accepted(self, client, sample_bundle):
        """CH-7: Message of exactly 1 character is accepted."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 10
        mock_provider.last_output_tokens = 5

        async def mock_chat(messages, tools, handler):
            yield "ok"

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.post(
                f"/api/chat/{session_id}", json={"message": "?"}
            )
        assert response.status_code == 200


class TestAnalyzeCachedReport:
    @pytest.mark.asyncio
    async def test_cached_report_returned_on_second_analyze(self, client, sample_bundle):
        """A-4: Analyzing a session that already has a report returns the cached report."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        # Directly set a report on the session
        session = session_store.get(session_id)
        session.report = DiagnosticReport(
            executive_summary="Cached result.",
            findings=[],
            signal_types_analyzed=["events"],
            truncation_notes=None,
        )

        # No provider needed — should return cached report immediately
        response = await client.get(f"/api/analyze/{session_id}")
        assert response.status_code == 200

        lines = response.text.strip().split("\n")
        events = [
            json.loads(l.replace("data: ", "").replace("data:", ""))
            for l in lines if l.startswith("data:")
        ]
        report_events = [e for e in events if e.get("type") == "report"]
        assert len(report_events) == 1
        assert report_events[0]["report"]["executive_summary"] == "Cached result."


class TestAnalyzeInvalidJson:
    @pytest.mark.asyncio
    async def test_invalid_json_from_llm_yields_parse_error(self, client, sample_bundle):
        """A-13: When the LLM response is not valid JSON, a parse error event is emitted."""
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

        async def mock_analyze(context):
            yield "This is not valid JSON at all."

        mock_provider.analyze = mock_analyze

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.get(f"/api/analyze/{session_id}")

        lines = response.text.strip().split("\n")
        events = [
            json.loads(l.replace("data: ", "").replace("data:", ""))
            for l in lines if l.startswith("data:")
        ]
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert "parse" in error_events[0]["message"].lower()


class TestUploadWarnings:
    @pytest.mark.asyncio
    async def test_upload_with_skipped_files_includes_warnings(self, client):
        """U-5: Upload response includes warnings when files are skipped."""
        import io
        import tarfile

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # Unsafe path — will be skipped
            evil_data = b"evil"
            evil_info = tarfile.TarInfo(name="../../etc/shadow")
            evil_info.size = len(evil_data)
            tar.addfile(evil_info, io.BytesIO(evil_data))
            # Normal file
            ok_data = b"ok"
            ok_info = tarfile.TarInfo(name="bundle/ok.txt")
            ok_info.size = len(ok_data)
            tar.addfile(ok_info, io.BytesIO(ok_data))

        response = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", buf.getvalue(), "application/gzip")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "warnings" in data
        assert any("unsafe" in w for w in data["warnings"])
        assert data["manifest"]["total_files"] == 1


class TestChatToolUse:
    @pytest.mark.asyncio
    async def test_tool_handler_returns_file_contents(self, client, sample_bundle):
        """CH-12/CH-13: LLM invokes get_file_contents and receives decoded file content."""
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
            # Simulate the LLM calling the tool
            result = tool_handler("get_file_contents", {"file_path": "bundle/events.json"})
            assert "OOMKilling" in result
            # Then yield the tool sentinel and a text response
            yield TOOL_USE_SENTINEL + json.dumps({
                "type": "tool_use",
                "name": "get_file_contents",
                "file_path": "bundle/events.json",
            })
            yield "I found OOM events in the bundle."

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.post(
                f"/api/chat/{session_id}",
                json={"message": "Check the events"},
            )

        assert response.status_code == 200
        lines = response.text.strip().split("\n")
        events = [
            json.loads(l.replace("data: ", "").replace("data:", ""))
            for l in lines if l.startswith("data:")
        ]
        # Should have tool_use event, chunk events, and done
        tool_events = [e for e in events if e.get("type") == "tool_use"]
        assert len(tool_events) == 1
        assert tool_events[0]["name"] == "get_file_contents"

        chunk_events = [e for e in events if e.get("type") == "chunk"]
        assert any("OOM" in e["content"] for e in chunk_events)

    @pytest.mark.asyncio
    async def test_tool_handler_file_not_found(self, client, sample_bundle):
        """CH-14: Requesting a file that doesn't exist returns an error message."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 10
        mock_provider.last_output_tokens = 5

        async def mock_chat(messages, tools, tool_handler):
            result = tool_handler("get_file_contents", {"file_path": "nonexistent/file.txt"})
            assert "not found" in result.lower()
            yield "File was not found."

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.post(
                f"/api/chat/{session_id}",
                json={"message": "Read a missing file"},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_tool_handler_unknown_tool(self, client, sample_bundle):
        """CH-16: Calling an unknown tool returns an error message."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 10
        mock_provider.last_output_tokens = 5

        async def mock_chat(messages, tools, tool_handler):
            result = tool_handler("delete_everything", {})
            assert "Unknown tool" in result
            yield "Done."

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.post(
                f"/api/chat/{session_id}",
                json={"message": "Do something bad"},
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_assistant_response_saved_to_history(self, client, sample_bundle):
        """CH-3: The assistant's non-empty response is saved to chat history."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 10
        mock_provider.last_output_tokens = 5

        async def mock_chat(messages, tools, handler):
            yield "Here is my analysis."

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.post(
                f"/api/chat/{session_id}",
                json={"message": "What's wrong?"},
            )

        session = session_store.get(session_id)
        # Should have user message + assistant message
        assert len(session.chat_history) == 2
        assert session.chat_history[0].role == "user"
        assert session.chat_history[1].role == "assistant"
        assert "analysis" in session.chat_history[1].content

    @pytest.mark.asyncio
    async def test_empty_assistant_response_not_saved(self, client, sample_bundle):
        """CH-11: An empty/whitespace-only assistant response is not saved."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"
        mock_provider.last_input_tokens = 10
        mock_provider.last_output_tokens = 5

        async def mock_chat(messages, tools, handler):
            yield "   "  # whitespace only

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.post(
                f"/api/chat/{session_id}",
                json={"message": "hello"},
            )

        session = session_store.get(session_id)
        # Only the user message should be saved, not the whitespace response
        assert len(session.chat_history) == 1
        assert session.chat_history[0].role == "user"


class TestFileRetrieval:
    @pytest.mark.asyncio
    async def test_get_file_contents_success(self, client, sample_bundle):
        """GET /api/files/{session_id}/{file_path} returns file content."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        response = await client.get(
            f"/api/files/{session_id}/bundle/events.json"
        )
        assert response.status_code == 200
        assert '[{"reason":"OOMKilling"}]' in response.text

    @pytest.mark.asyncio
    async def test_get_file_not_found(self, client, sample_bundle):
        """GET a non-existent file path returns 404."""
        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", sample_bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        response = await client.get(
            f"/api/files/{session_id}/bundle/nonexistent.log"
        )
        assert response.status_code == 404
        assert "File not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_file_session_not_found(self, client):
        """GET a file with a non-existent session ID returns 404."""
        response = await client.get(
            "/api/files/no-such-session/bundle/events.json"
        )
        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_file_utf8_content(self, client):
        """GET returns plain text with correct UTF-8 content."""
        utf8_content = "line1: hello world\nline2: résumé café"
        bundle = make_tar_gz({
            "bundle/readme.txt": utf8_content.encode("utf-8"),
        })

        upload_resp = await client.post(
            "/api/upload",
            files={"file": ("bundle.tar.gz", bundle, "application/gzip")},
        )
        session_id = upload_resp.json()["session_id"]

        response = await client.get(
            f"/api/files/{session_id}/bundle/readme.txt"
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == utf8_content
