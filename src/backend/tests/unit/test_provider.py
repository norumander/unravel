"""Unit tests for LLM provider interface and factory."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.provider import LLMError, get_provider


class TestGetProviderFactory:
    def test_no_provider_set_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="LLM_PROVIDER"):
                get_provider()

    def test_unknown_provider_raises_error(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}):
            with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
                get_provider()

    def test_anthropic_without_key_raises_error(self):
        env = {"LLM_PROVIDER": "anthropic"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                get_provider()

    def test_openai_without_key_raises_error(self):
        env = {"LLM_PROVIDER": "openai"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                get_provider()

    def test_anthropic_with_key_returns_provider(self):
        env = {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key-123"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert provider.provider_name == "anthropic"

    def test_openai_with_key_returns_provider(self):
        env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key-123"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert provider.provider_name == "openai"

    def test_case_insensitive_provider_name(self):
        env = {"LLM_PROVIDER": "Anthropic", "ANTHROPIC_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert provider.provider_name == "anthropic"


class TestAnthropicProvider:
    def test_model_name_default(self):
        env = {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert "claude" in provider.model_name

    def test_model_name_custom(self):
        env = {
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "test-key",
            "ANTHROPIC_MODEL": "claude-3-haiku-20240307",
        }
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert provider.model_name == "claude-3-haiku-20240307"


class TestOpenAIProvider:
    def test_model_name_default(self):
        env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert provider.model_name == "gpt-4o"

    def test_model_name_custom(self):
        env = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-4-turbo",
        }
        with patch.dict(os.environ, env, clear=True):
            provider = get_provider()
            assert provider.model_name == "gpt-4-turbo"


class TestLLMError:
    def test_llm_error_is_exception(self):
        err = LLMError("something broke")
        assert isinstance(err, Exception)
        assert str(err) == "something broke"
