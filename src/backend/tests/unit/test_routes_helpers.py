"""Unit tests for route helper functions."""

from app.api.routes import _strip_markdown_fences


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
