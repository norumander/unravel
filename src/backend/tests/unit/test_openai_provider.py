"""Unit tests for OpenAI provider with mocked SDK responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.openai_provider import OpenAIProvider
from app.llm.provider import LLMError
from app.models.schemas import (
    AnalysisContext,
    BundleFile,
    BundleManifest,
    ChatMessage,
    SignalType,
)


@pytest.fixture
def provider():
    return OpenAIProvider(api_key="test-key")


@pytest.fixture
def sample_context():
    manifest = BundleManifest(
        total_files=1,
        total_size_bytes=100,
        files=[BundleFile(path="events.json", size_bytes=100, signal_type=SignalType.events)],
    )
    return AnalysisContext(
        signal_contents={SignalType.events: "event data"},
        manifest=manifest,
    )


@pytest.fixture
def mock_report_json():
    return (
        '{"executive_summary":"Test summary","findings":[{'
        '"severity":"warning","title":"Test","description":"Desc",'
        '"root_cause":"Cause","remediation":"Fix","source_signals":["events"]'
        '}],"signal_types_analyzed":["events"],"truncation_notes":null}'
    )


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_streams_text(self, provider, sample_context, mock_report_json):
        chunks = [mock_report_json[:20], mock_report_json[20:]]

        mock_chunk_objs = []
        for text in chunks:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = text
            chunk.usage = None
            mock_chunk_objs.append(chunk)

        # Final chunk with usage
        usage_chunk = MagicMock()
        usage_chunk.choices = []
        usage_chunk.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        mock_chunk_objs.append(usage_chunk)

        async def mock_stream():
            for c in mock_chunk_objs:
                yield c

        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_stream(),
        ):
            collected = ""
            async for text in provider.analyze(sample_context):
                collected += text

            assert collected == mock_report_json
            assert provider.last_input_tokens == 100
            assert provider.last_output_tokens == 50

    @pytest.mark.asyncio
    async def test_analyze_auth_error_raises_llm_error(self, provider, sample_context):
        import openai

        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            side_effect=openai.AuthenticationError(
                message="invalid key",
                response=MagicMock(status_code=401),
                body={"error": {"message": "invalid key"}},
            ),
        ):
            with pytest.raises(LLMError, match="authentication"):
                async for _ in provider.analyze(sample_context):
                    pass


class TestChat:
    @pytest.mark.asyncio
    async def test_chat_streams_text_without_tool_use(self, provider):
        messages = [ChatMessage(role="user", content="What's wrong?")]
        tools = [
            {
                "name": "get_file_contents",
                "description": "Get file contents",
                "parameters": {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                    "required": ["file_path"],
                },
            }
        ]

        chunks = []
        for text in ["The pod is ", "crash-looping."]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = text
            chunk.choices[0].delta.tool_calls = None
            chunk.usage = None
            chunks.append(chunk)

        # Usage chunk
        usage = MagicMock()
        usage.choices = []
        usage.usage = MagicMock(prompt_tokens=50, completion_tokens=30)
        chunks.append(usage)

        async def mock_stream():
            for c in chunks:
                yield c

        with patch.object(
            provider._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=mock_stream(),
        ):
            collected = ""
            async for text in provider.chat(messages, tools, lambda n, a: ""):
                collected += text

            assert "crash-looping" in collected
