"""Shared test fixtures for the Unravel backend test suite."""

import pytest

from app.models.schemas import (
    AnalysisContext,
    BundleFile,
    BundleManifest,
    SignalType,
)


@pytest.fixture
def sample_context():
    """Analysis context with a single events file — used by both provider test suites."""
    manifest = BundleManifest(
        total_files=1,
        total_size_bytes=100,
        files=[BundleFile(path="events.json", size_bytes=100, signal_type=SignalType.events)],
    )
    return AnalysisContext(
        signal_contents={SignalType.events: "event data"},
        manifest=manifest,
    )


@pytest.fixture
def mock_report_json():
    """Minimal valid DiagnosticReport JSON string — used by both provider test suites."""
    return (
        '{"executive_summary":"Test summary","findings":[{'
        '"severity":"warning","title":"Test","description":"Desc",'
        '"root_cause":"Cause","remediation":"Fix","source_signals":["events"]'
        '}],"signal_types_analyzed":["events"],"truncation_notes":null}'
    )
