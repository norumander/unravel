"""Unit tests for route helper functions."""

import json

from app.api.routes import _sanitize_signal_types, _strip_markdown_fences


class TestStripMarkdownFences:
    def test_plain_json_unchanged(self):
        json_str = '{"key": "value"}'
        assert _strip_markdown_fences(json_str) == json_str

    def test_strips_json_fence(self):
        fenced = '```json\n{"key": "value"}\n```'
        assert _strip_markdown_fences(fenced) == '{"key": "value"}'

    def test_strips_plain_fence(self):
        fenced = '```\n{"key": "value"}\n```'
        assert _strip_markdown_fences(fenced) == '{"key": "value"}'

    def test_strips_with_surrounding_whitespace(self):
        fenced = '  ```json\n{"key": "value"}\n```  '
        assert _strip_markdown_fences(fenced) == '{"key": "value"}'

    def test_multiline_json_preserved(self):
        inner = '{\n  "a": 1,\n  "b": 2\n}'
        fenced = f'```json\n{inner}\n```'
        assert _strip_markdown_fences(fenced) == inner

    def test_no_fences_returns_original(self):
        text = "just some text"
        assert _strip_markdown_fences(text) == text


class TestSanitizeSignalTypes:
    """Tests for _sanitize_signal_types — the AI output boundary layer.

    LLMs produce structured JSON but occasionally invent values outside the
    expected schema. These tests verify that the sanitizer normalizes unknown
    enum values to "other" rather than letting Pydantic reject the entire
    report. This is the critical seam between unpredictable AI output and
    the application's type system.
    """

    def test_valid_signal_types_unchanged(self):
        """Known signal types pass through unmodified."""
        data = {
            "findings": [{"source_signals": ["pod_logs", "events"]}],
            "signal_types_analyzed": ["pod_logs", "events", "cluster_info"],
        }
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert result["findings"][0]["source_signals"] == ["pod_logs", "events"]
        assert result["signal_types_analyzed"] == ["pod_logs", "events", "cluster_info"]

    def test_unknown_signal_types_mapped_to_other(self):
        """LLM-invented signal types (e.g., 'node_conditions') become 'other'."""
        data = {
            "findings": [{"source_signals": ["pod_logs", "node_conditions", "pod_status"]}],
            "signal_types_analyzed": ["pod_logs", "node_conditions"],
        }
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert result["findings"][0]["source_signals"] == ["pod_logs", "other", "other"]
        assert result["signal_types_analyzed"] == ["pod_logs", "other"]

    def test_all_six_valid_types_pass_through(self):
        """All enum members are recognized."""
        all_types = ["pod_logs", "cluster_info", "resource_definitions", "events", "node_status", "other"]
        data = {
            "findings": [{"source_signals": all_types}],
            "signal_types_analyzed": all_types,
        }
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert result["findings"][0]["source_signals"] == all_types
        assert result["signal_types_analyzed"] == all_types

    def test_empty_findings_handled(self):
        """Reports with no findings don't crash."""
        data = {"findings": [], "signal_types_analyzed": ["events"]}
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert result["findings"] == []

    def test_missing_source_signals_key_tolerated(self):
        """Findings without source_signals key are left alone."""
        data = {
            "findings": [{"title": "No signals field"}],
            "signal_types_analyzed": ["events"],
        }
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert "source_signals" not in result["findings"][0]

    def test_missing_signal_types_analyzed_tolerated(self):
        """Reports without signal_types_analyzed are left alone."""
        data = {"findings": [{"source_signals": ["events"]}]}
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert "signal_types_analyzed" not in result

    def test_invalid_json_returned_unchanged(self):
        """Non-JSON input passes through for downstream error handling."""
        bad_input = "this is not json at all"
        assert _sanitize_signal_types(bad_input) == bad_input

    def test_truncated_json_returned_unchanged(self):
        """Truncated LLM output (incomplete JSON) passes through."""
        truncated = '{"findings": [{"source_signals": ["pod_logs"'
        assert _sanitize_signal_types(truncated) == truncated

    def test_multiple_findings_each_sanitized(self):
        """Sanitization applies to every finding, not just the first."""
        data = {
            "findings": [
                {"source_signals": ["pod_logs", "custom_metric"]},
                {"source_signals": ["events", "deployment_status"]},
                {"source_signals": ["cluster_info"]},
            ],
            "signal_types_analyzed": ["pod_logs", "events", "cluster_info"],
        }
        result = json.loads(_sanitize_signal_types(json.dumps(data)))
        assert result["findings"][0]["source_signals"] == ["pod_logs", "other"]
        assert result["findings"][1]["source_signals"] == ["events", "other"]
        assert result["findings"][2]["source_signals"] == ["cluster_info"]
