"""LLM provider interface and factory."""

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.models.schemas import AnalysisContext, ChatMessage


class LLMError(Exception):
    """Raised when an LLM API call fails."""


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'anthropic', 'openai')."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name being used."""

    @abstractmethod
    async def analyze(self, context: AnalysisContext) -> AsyncIterator[str]:
        """Stream analysis of bundle content, yielding text chunks.

        The complete concatenation of all yielded chunks should be a valid
        JSON string representing a DiagnosticReport.
        """
        yield ""  # pragma: no cover

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        tool_handler: Callable[[str, dict], str],
    ) -> AsyncIterator[str]:
        """Stream a chat response, yielding text chunks.

        When the LLM requests a tool call, the tool_handler is invoked
        and the result is fed back into the conversation.
        """
        yield ""  # pragma: no cover


def get_provider() -> LLMProvider:
    """Factory function to create the configured LLM provider.

    Reads LLM_PROVIDER env var to select the implementation.
    Validates that the required API key is present.

    Raises:
        ValueError: If LLM_PROVIDER is not set or is unknown.
        ValueError: If the required API key env var is missing.
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
