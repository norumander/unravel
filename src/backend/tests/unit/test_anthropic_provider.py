"""Unit tests for Anthropic provider with mocked SDK responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.anthropic_provider import AnthropicProvider
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
    return AnthropicProvider(api_key="test-key")


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
        # Mock the streaming response
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        # Simulate streaming text
        chunks = [mock_report_json[:20], mock_report_json[20:]]

        async def mock_text_stream():
            for chunk in chunks:
                yield chunk

        mock_stream.text_stream = mock_text_stream()

        # Mock get_final_message
        mock_final = MagicMock()
        mock_final.usage.input_tokens = 100
        mock_final.usage.output_tokens = 50
        mock_stream.get_final_message = AsyncMock(return_value=mock_final)

        with patch.object(provider._client.messages, "stream", return_value=mock_stream):
            collected = ""
            async for text in provider.analyze(sample_context):
                collected += text

            assert collected == mock_report_json
            assert provider.last_input_tokens == 100
            assert provider.last_output_tokens == 50

    @pytest.mark.asyncio
    async def test_analyze_auth_error_raises_llm_error(self, provider, sample_context):
        import anthropic

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(
            side_effect=anthropic.AuthenticationError(
                message="invalid key",
                response=MagicMock(status_code=401),
                body={"error": {"message": "invalid key"}},
            )
        )
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        with patch.object(provider._client.messages, "stream", return_value=mock_stream):
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

        # Mock streaming response events
        mock_events = [
            MagicMock(
                type="message_start",
                message=MagicMock(usage=MagicMock(input_tokens=50)),
            ),
            MagicMock(
                type="content_block_start",
                content_block=MagicMock(type="text"),
            ),
            MagicMock(
                type="content_block_delta",
                delta=MagicMock(type="text_delta", text="The pod is "),
            ),
            MagicMock(
                type="content_block_delta",
                delta=MagicMock(type="text_delta", text="crash-looping."),
            ),
            MagicMock(
                type="content_block_stop",
            ),
            MagicMock(
                type="message_delta",
                usage=MagicMock(output_tokens=30),
            ),
        ]

        async def mock_iter():
            for event in mock_events:
                yield event

        with patch.object(
            provider._client.messages, "create", new_callable=AsyncMock, return_value=mock_iter()
        ):
            collected = ""
            async for text in provider.chat(messages, tools, lambda n, a: ""):
                collected += text

            assert "crash-looping" in collected
