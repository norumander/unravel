"""Integration tests for LLM error handling and resilience."""

import io
import json
import tarfile
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import reset_provider
from app.llm.provider import LLMError
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


@pytest.fixture(autouse=True)
def clear_state():
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


@pytest.fixture
def sample_bundle():
    return _make_tar_gz({"bundle/events.json": b'[{"reason":"test"}]'})


async def _upload(client, bundle):
    resp = await client.post(
        "/api/upload", files={"file": ("b.tar.gz", bundle, "application/gzip")}
    )
    return resp.json()["session_id"]


class TestAnalyzeErrorHandling:
    @pytest.mark.asyncio
    async def test_auth_error_returns_sse_error(self, client, sample_bundle):
        session_id = await _upload(client, sample_bundle)

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"

        async def mock_analyze(context):
            raise LLMError("Anthropic API authentication failed. Check your ANTHROPIC_API_KEY.")
            yield  # noqa: unreachable — makes this an async generator

        mock_provider.analyze = mock_analyze

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.get(f"/api/analyze/{session_id}")

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert "authentication" in error_events[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_no_provider_configured_returns_error(self, client, sample_bundle):
        session_id = await _upload(client, sample_bundle)

        with patch("app.api.routes._get_or_create_provider", side_effect=ValueError("LLM_PROVIDER not set")):
            response = await client.get(f"/api/analyze/{session_id}")

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1

    @pytest.mark.asyncio
    async def test_session_usable_after_error(self, client, sample_bundle):
        session_id = await _upload(client, sample_bundle)

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"

        async def mock_analyze_error(context):
            raise LLMError("Rate limit exceeded")
            yield  # noqa

        mock_provider.analyze = mock_analyze_error

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.get(f"/api/analyze/{session_id}")

        # Session should still exist and be usable
        session = session_store.get(session_id)
        assert session is not None


class TestChatErrorHandling:
    @pytest.mark.asyncio
    async def test_chat_auth_error_returns_sse_error(self, client, sample_bundle):
        session_id = await _upload(client, sample_bundle)

        mock_provider = MagicMock()
        mock_provider.provider_name = "openai"
        mock_provider.model_name = "gpt-4o"

        async def mock_chat(messages, tools, handler):
            raise LLMError("OpenAI API authentication failed.")
            yield  # noqa

        mock_provider.chat = mock_chat

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            response = await client.post(
                f"/api/chat/{session_id}", json={"message": "hello"}
            )

        events = _parse_sse_events(response.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert "authentication" in error_events[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_session_usable_after_chat_error(self, client, sample_bundle):
        session_id = await _upload(client, sample_bundle)

        mock_provider = MagicMock()
        mock_provider.provider_name = "anthropic"
        mock_provider.model_name = "claude-test"

        async def mock_chat_error(messages, tools, handler):
            raise LLMError("Network timeout")
            yield  # noqa

        mock_provider.chat = mock_chat_error

        with patch("app.api.routes._get_or_create_provider", return_value=mock_provider):
            await client.post(f"/api/chat/{session_id}", json={"message": "hello"})

        # Session should still exist
        session = session_store.get(session_id)
        assert session is not None


def _parse_sse_events(text: str) -> list[dict]:
    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str and data_str != "[DONE]":
                try:
                    events.append(json.loads(data_str))
                except json.JSONDecodeError:
                    pass
    return events
