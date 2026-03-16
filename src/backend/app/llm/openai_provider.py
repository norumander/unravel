"""OpenAI GPT LLM provider implementation."""

import json
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import openai

from app.llm.prompts import ANALYSIS_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, build_analysis_prompt
from app.llm.provider import MAX_OUTPUT_TOKENS, LLMError, LLMProvider
from app.models.schemas import AnalysisContext, ChatMessage


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
                max_tokens=MAX_OUTPUT_TOKENS,
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

        except openai.AuthenticationError as e:
            raise LLMError(
                "OpenAI API authentication failed. Check your OPENAI_API_KEY."
            ) from e
        except openai.RateLimitError as e:
            raise LLMError("OpenAI API rate limit exceeded. Please retry later.") from e
        except openai.APIConnectionError as e:
            raise LLMError(
                "Failed to connect to OpenAI API. Check your network connection."
            ) from e
        except openai.APIStatusError as e:
            raise LLMError(f"OpenAI API error: {e.message}") from e

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
            while True:
                stream = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=MAX_OUTPUT_TOKENS,
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
                    tool_input = json.loads(tc_info["function"]["arguments"])
                    tool_name = tc_info["function"]["name"]

                    # Yield tool-use indicator as proper JSON
                    yield "\n" + json.dumps({
                        "type": "tool_use",
                        "name": tool_name,
                        "file_path": tool_input.get("file_path", ""),
                    }) + "\n"

                    result = tool_handler(tool_name, tool_input)
                    api_messages.append({
                        "role": "tool",
                        "tool_call_id": tc_info["id"],
                        "content": result,
                    })

        except openai.AuthenticationError as e:
            raise LLMError(
                "OpenAI API authentication failed. Check your OPENAI_API_KEY."
            ) from e
        except openai.RateLimitError as e:
            raise LLMError("OpenAI API rate limit exceeded. Please retry later.") from e
        except openai.APIConnectionError as e:
            raise LLMError(
                "Failed to connect to OpenAI API. Check your network connection."
            ) from e
        except openai.APIStatusError as e:
            raise LLMError(f"OpenAI API error: {e.message}") from e


def _build_api_messages(messages: list[ChatMessage]) -> list[dict]:
    """Convert internal ChatMessage objects to OpenAI API message format."""
    api_msgs: list[dict] = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            api_msgs.append({"role": msg.role, "content": msg.content})
    return api_msgs
