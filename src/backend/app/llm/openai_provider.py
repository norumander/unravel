"""OpenAI GPT LLM provider implementation."""

import json
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import openai

from app.llm.prompts import ANALYSIS_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, build_analysis_prompt
from app.llm.provider import (
    MAX_TOOL_ROUNDS,
    TOOL_USE_SENTINEL,
    LLMError,
    LLMProvider,
    get_max_output_tokens,
)
from app.models.schemas import AnalysisContext, ChatMessage


def _map_openai_error(e: Exception) -> LLMError:
    """Convert OpenAI SDK exceptions to LLMError."""
    if isinstance(e, openai.AuthenticationError):
        return LLMError("OpenAI API authentication failed. Check your OPENAI_API_KEY.")
    if isinstance(e, openai.RateLimitError):
        return LLMError("OpenAI API rate limit exceeded. Please retry later.")
    if isinstance(e, openai.APIConnectionError):
        return LLMError("Failed to connect to OpenAI API. Check your network connection.")
    if isinstance(e, openai.APIStatusError):
        return LLMError(f"OpenAI API error: {e.message}")
    return LLMError(f"Unexpected OpenAI error: {e}")


class OpenAIProvider(LLMProvider):
    """LLM provider using the OpenAI GPT API."""

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def analyze(self, context: AnalysisContext) -> AsyncIterator[str]:
        """Stream analysis of bundle content using OpenAI."""
        user_prompt = build_analysis_prompt(context)

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=get_max_output_tokens(),
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                if chunk.usage:
                    self._last_input_tokens = chunk.usage.prompt_tokens
                    self._last_output_tokens = chunk.usage.completion_tokens
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except (
            openai.AuthenticationError,
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APIStatusError,
        ) as e:
            raise _map_openai_error(e) from e

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        tool_handler: Callable[[str, dict], str],
    ) -> AsyncIterator[str]:
        """Stream a chat response using OpenAI with tool-use support."""
        api_messages = _build_api_messages(messages)

        api_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ] if tools else None

        try:
            for _round in range(MAX_TOOL_ROUNDS):
                stream = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=get_max_output_tokens(),
                    messages=[
                        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                        *api_messages,
                    ],
                    tools=api_tools if api_tools else openai.NOT_GIVEN,
                    stream=True,
                    stream_options={"include_usage": True},
                )

                collected_text = ""
                tool_calls_by_index: dict[int, dict] = {}

                async for chunk in stream:
                    if chunk.usage:
                        self._last_input_tokens = chunk.usage.prompt_tokens
                        self._last_output_tokens = chunk.usage.completion_tokens

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    if delta.content:
                        yield delta.content
                        collected_text += delta.content

                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_by_index:
                                tool_calls_by_index[idx] = {
                                    "id": tc.id or "",
                                    "name": tc.function.name or "" if tc.function else "",
                                    "arguments": "",
                                }
                            if tc.function and tc.function.arguments:
                                tool_calls_by_index[idx]["arguments"] += tc.function.arguments
                            if tc.id:
                                tool_calls_by_index[idx]["id"] = tc.id
                            if tc.function and tc.function.name:
                                tool_calls_by_index[idx]["name"] = tc.function.name

                if not tool_calls_by_index:
                    break

                assistant_tool_calls = []
                for _idx, tc_data in sorted(tool_calls_by_index.items()):
                    assistant_tool_calls.append({
                        "id": tc_data["id"],
                        "type": "function",
                        "function": {
                            "name": tc_data["name"],
                            "arguments": tc_data["arguments"],
                        },
                    })

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "tool_calls": assistant_tool_calls,
                }
                if collected_text:
                    assistant_msg["content"] = collected_text
                api_messages.append(assistant_msg)

                for tc_info in assistant_tool_calls:
                    try:
                        tool_input = json.loads(tc_info["function"]["arguments"])
                    except json.JSONDecodeError:
                        api_messages.append({
                            "role": "tool",
                            "tool_call_id": tc_info["id"],
                            "content": "Error: malformed tool arguments",
                        })
                        continue

                    tool_name = tc_info["function"]["name"]

                    yield TOOL_USE_SENTINEL + json.dumps({
                        "type": "tool_use",
                        "name": tool_name,
                        "file_path": tool_input.get("file_path", ""),
                    })

                    result = tool_handler(tool_name, tool_input)
                    api_messages.append({
                        "role": "tool",
                        "tool_call_id": tc_info["id"],
                        "content": result,
                    })
            else:
                yield "\n[Tool call limit reached — stopping after "
                yield f"{MAX_TOOL_ROUNDS} rounds]\n"

        except (
            openai.AuthenticationError,
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APIStatusError,
        ) as e:
            raise _map_openai_error(e) from e


def _build_api_messages(messages: list[ChatMessage]) -> list[dict]:
    """Convert internal ChatMessage objects to OpenAI API message format."""
    api_msgs: list[dict] = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            api_msgs.append({"role": msg.role, "content": msg.content})
    return api_msgs
