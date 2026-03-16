"""Anthropic Claude LLM provider implementation."""

import json
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import anthropic

from app.llm.prompts import ANALYSIS_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, build_analysis_prompt
from app.llm.provider import MAX_OUTPUT_TOKENS, LLMError, LLMProvider
from app.models.schemas import AnalysisContext, ChatMessage


class AnthropicProvider(LLMProvider):
    """LLM provider using the Anthropic Claude API."""

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    async def analyze(self, context: AnalysisContext) -> AsyncIterator[str]:
        """Stream analysis of bundle content using Claude."""
        user_prompt = build_analysis_prompt(context)

        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=ANALYSIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

                response = await stream.get_final_message()
                self._last_input_tokens = response.usage.input_tokens
                self._last_output_tokens = response.usage.output_tokens

        except anthropic.AuthenticationError as e:
            raise LLMError(
                "Anthropic API authentication failed. Check your ANTHROPIC_API_KEY."
            ) from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic API rate limit exceeded. Please retry later.") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(
                "Failed to connect to Anthropic API. Check your network connection."
            ) from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error: {e.message}") from e

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        tool_handler: Callable[[str, dict], str],
    ) -> AsyncIterator[str]:
        """Stream a chat response using Claude with tool-use support."""
        api_messages = _build_api_messages(messages)

        api_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]

        try:
            while True:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    system=CHAT_SYSTEM_PROMPT,
                    messages=api_messages,
                    tools=api_tools if api_tools else anthropic.NOT_GIVEN,
                    stream=True,
                )

                collected_text = ""
                tool_use_blocks: list[dict] = []
                current_tool: dict | None = None

                async for event in response:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            current_tool = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                                "input_json": "",
                            }
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield event.delta.text
                            collected_text += event.delta.text
                        elif event.delta.type == "input_json_delta":
                            if current_tool:
                                current_tool["input_json"] += event.delta.partial_json
                    elif event.type == "content_block_stop":
                        if current_tool:
                            tool_use_blocks.append(current_tool)
                            current_tool = None
                    elif event.type == "message_delta":
                        if hasattr(event.usage, "output_tokens"):
                            self._last_output_tokens = event.usage.output_tokens
                    elif event.type == "message_start":
                        if hasattr(event.message, "usage"):
                            self._last_input_tokens = event.message.usage.input_tokens

                if not tool_use_blocks:
                    break

                # Process tool calls
                assistant_content: list[dict] = []
                if collected_text:
                    assistant_content.append({"type": "text", "text": collected_text})

                tool_results: list[dict] = []
                for tool_block in tool_use_blocks:
                    tool_input = json.loads(tool_block["input_json"])
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tool_block["id"],
                        "name": tool_block["name"],
                        "input": tool_input,
                    })

                    # Yield tool-use indicator as proper JSON
                    yield "\n" + json.dumps({
                        "type": "tool_use",
                        "name": tool_block["name"],
                        "file_path": tool_input.get("file_path", ""),
                    }) + "\n"

                    result = tool_handler(tool_block["name"], tool_input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block["id"],
                        "content": result,
                    })

                api_messages.append({"role": "assistant", "content": assistant_content})
                api_messages.append({"role": "user", "content": tool_results})

        except anthropic.AuthenticationError as e:
            raise LLMError(
                "Anthropic API authentication failed. Check your ANTHROPIC_API_KEY."
            ) from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic API rate limit exceeded. Please retry later.") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(
                "Failed to connect to Anthropic API. Check your network connection."
            ) from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error: {e.message}") from e


def _build_api_messages(messages: list[ChatMessage]) -> list[dict]:
    """Convert internal ChatMessage objects to Anthropic API message format."""
    api_msgs: list[dict] = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            api_msgs.append({"role": msg.role, "content": msg.content})
    return api_msgs
