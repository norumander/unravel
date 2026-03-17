"""Unit tests for LLM prompt building functions."""

import pytest

from app.llm.prompts import build_analysis_prompt, _signal_type_label
from app.models.schemas import AnalysisContext, BundleFile, BundleManifest, SignalType


def _make_manifest(total_files: int = 3) -> BundleManifest:
    """Create a minimal BundleManifest for testing."""
    return BundleManifest(total_files=total_files, total_size_bytes=1024, files=[])


def _make_context(
    signal_contents: dict[SignalType, str] | None = None,
    truncation_notes: str | None = None,
    total_files: int = 3,
) -> AnalysisContext:
    """Create an AnalysisContext with sensible defaults for testing."""
    return AnalysisContext(
        signal_contents=signal_contents or {},
        truncation_notes=truncation_notes,
        manifest=_make_manifest(total_files=total_files),
    )


class TestBuildAnalysisPrompt:
    """Tests for build_analysis_prompt."""

    def test_build_prompt_minimal_context_includes_header(self):
        """PR-1: Prompt always includes the Support Bundle Analysis header."""
        ctx = _make_context()
        result = build_analysis_prompt(ctx)
        assert "# Support Bundle Analysis" in result

    def test_build_prompt_with_truncation_notes_includes_note(self):
        """PR-2: Prompt includes truncation notes when present."""
        ctx = _make_context(truncation_notes="Large files were trimmed to 50KB")
        result = build_analysis_prompt(ctx)
        assert "**Note:** Some content was truncated: Large files were trimmed to 50KB" in result

    def test_build_prompt_without_truncation_notes_omits_note(self):
        """PR-3: Prompt omits truncation notes when truncation_notes is None."""
        ctx = _make_context(truncation_notes=None)
        result = build_analysis_prompt(ctx)
        assert "**Note:**" not in result
        assert "truncated" not in result

    def test_build_prompt_includes_manifest_file_count(self):
        """PR-4: Prompt includes the manifest total file count."""
        ctx = _make_context(total_files=42)
        result = build_analysis_prompt(ctx)
        assert "Total files: 42" in result

    def test_build_prompt_includes_labeled_signal_sections(self):
        """PR-5: Prompt includes labeled sections for each signal type."""
        signals = {
            SignalType.events: "CrashLoopBackOff detected",
            SignalType.pod_logs: "Error: OOMKilled",
        }
        ctx = _make_context(signal_contents=signals)
        result = build_analysis_prompt(ctx)
        assert "## Events" in result
        assert "CrashLoopBackOff detected" in result
        assert "## Pod Logs" in result
        assert "Error: OOMKilled" in result

    def test_build_prompt_empty_signals_has_header_and_manifest_only(self):
        """PR-7: Empty signal_contents produces prompt with only header and manifest."""
        ctx = _make_context(signal_contents={}, total_files=5)
        result = build_analysis_prompt(ctx)
        assert "# Support Bundle Analysis" in result
        assert "Total files: 5" in result
        # No signal-type section headers should appear
        for label in ["Events", "Pod Logs", "Cluster Info", "Resource Definitions", "Node Status", "Other"]:
            assert f"## {label}" not in result


class TestSignalTypeLabel:
    """PR-6: Tests for _signal_type_label producing correct human-readable labels."""

    @pytest.mark.parametrize(
        "signal_type, expected_label",
        [
            (SignalType.events, "Events"),
            (SignalType.pod_logs, "Pod Logs"),
            (SignalType.cluster_info, "Cluster Info"),
            (SignalType.resource_definitions, "Resource Definitions"),
            (SignalType.node_status, "Node Status"),
            (SignalType.other, "Other"),
        ],
    )
    def test_signal_type_label_returns_correct_label(self, signal_type, expected_label):
        assert _signal_type_label(signal_type) == expected_label
