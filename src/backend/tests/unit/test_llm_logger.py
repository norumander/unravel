"""Unit tests for structured LLM logger."""

import json

import pytest

from app.logging.llm_logger import LLMCallLogger


@pytest.fixture
def logger():
    return LLMCallLogger()


class TestLLMCallLogger:
    def test_emits_json_to_stdout(self, logger, capsys):
        with logger.track("session-123", "analyze", "anthropic", "claude-3") as tracker:
            tracker.input_tokens = 100
            tracker.output_tokens = 50

        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())

        assert entry["session_id"] == "session-123"
        assert entry["call_type"] == "analyze"
        assert entry["provider"] == "anthropic"
        assert entry["model"] == "claude-3"
        assert entry["input_tokens"] == 100
        assert entry["output_tokens"] == 50
        assert entry["status"] == "success"

    def test_all_required_fields_present(self, logger, capsys):
        required_fields = [
            "timestamp",
            "session_id",
            "call_type",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "latency_ms",
            "status",
        ]

        with logger.track("s1", "chat", "openai", "gpt-4o") as tracker:
            pass

        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())

        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    def test_latency_is_positive_integer(self, logger, capsys):
        with logger.track("s1", "analyze", "anthropic", "claude-3") as tracker:
            pass

        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())

        assert isinstance(entry["latency_ms"], int)
        assert entry["latency_ms"] >= 0

    def test_error_status_on_exception(self, logger, capsys):
        with pytest.raises(ValueError):
            with logger.track("s1", "analyze", "anthropic", "claude-3") as tracker:
                raise ValueError("test error")

        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())

        assert entry["status"] == "error"

    def test_chat_call_type(self, logger, capsys):
        with logger.track("s1", "chat", "openai", "gpt-4o") as tracker:
            tracker.input_tokens = 200
            tracker.output_tokens = 100

        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())

        assert entry["call_type"] == "chat"
        assert entry["provider"] == "openai"

    def test_no_bundle_content_in_logs(self, logger, capsys):
        """Verify that no bundle content leaks into log output (GR-6)."""
        with logger.track("s1", "analyze", "anthropic", "claude-3") as tracker:
            tracker.input_tokens = 100
            tracker.output_tokens = 50

        captured = capsys.readouterr()
        log_output = captured.out

        # The log should only contain the JSON structure, no file contents
        entry = json.loads(log_output.strip())
        for key, value in entry.items():
            if isinstance(value, str):
                # No key should contain file paths or content
                assert "log content" not in value.lower()
                assert "pod.log" not in value.lower()

    def test_timestamp_is_iso_format(self, logger, capsys):
        with logger.track("s1", "analyze", "anthropic", "claude-3") as tracker:
            pass

        captured = capsys.readouterr()
        entry = json.loads(captured.out.strip())

        # Should parse as ISO format
        from datetime import datetime

        datetime.fromisoformat(entry["timestamp"])
