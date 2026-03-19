"""LLM provider interface and factory."""

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.models.schemas import AnalysisContext, ChatMessage

TOOL_USE_SENTINEL = "\x00__TOOL_USE__"
MAX_TOOL_ROUNDS = 10


def get_max_output_tokens() -> int:
    """Read max output tokens from environment at call time, not import time."""
    return int(os.environ.get("LLM_MAX_TOKENS", "8192"))


class LLMError(Exception):
    """Raised when an LLM API call fails."""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self) -> None:
        self._last_input_tokens = 0
        self._last_output_tokens = 0

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    def last_input_tokens(self) -> int:
        return self._last_input_tokens

    @property
    def last_output_tokens(self) -> int:
        return self._last_output_tokens

    @abstractmethod
    async def analyze(
        self, context: AnalysisContext, extra_instruction: str | None = None
    ) -> AsyncIterator[str]:
        """Stream analysis, yielding text chunks that form a DiagnosticReport JSON."""
        yield ""  # pragma: no cover

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        tool_handler: Callable[[str, dict], str],
    ) -> AsyncIterator[str]:
        """Stream a chat response with tool-use support."""
        yield ""  # pragma: no cover


def get_provider() -> LLMProvider:
    """Create the configured LLM provider from environment variables.

    Raises:
        ValueError: If LLM_PROVIDER is not set or unknown, or if the required API key is missing.
    """
    provider = os.environ.get("LLM_PROVIDER", "").lower()

    if not provider:
        raise ValueError(
            "LLM_PROVIDER environment variable is not set. "
            "Set it to 'anthropic' or 'openai'."
        )

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required "
                "when LLM_PROVIDER=anthropic."
            )
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=api_key)

    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required "
                "when LLM_PROVIDER=openai."
            )
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=api_key)

    raise ValueError(
        f"Unknown LLM_PROVIDER: '{provider}'. Must be 'anthropic' or 'openai'."
    )


def get_fallback_provider() -> LLMProvider | None:
    """Try to create the alternative LLM provider for fallback.

    If primary is anthropic, tries openai and vice versa.
    Returns None if the fallback provider's API key is not configured.
    """
    primary = os.environ.get("LLM_PROVIDER", "").lower()

    if primary == "anthropic":
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            from app.llm.openai_provider import OpenAIProvider
            return OpenAIProvider(api_key=api_key)
    elif primary == "openai":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            from app.llm.anthropic_provider import AnthropicProvider
            return AnthropicProvider(api_key=api_key)

    return None
