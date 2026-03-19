"""Unit tests for programmatic quality evaluator."""

from app.evals.evaluator import (
    check_citation_accuracy,
    check_coverage,
    run_programmatic_evals,
    build_retry_feedback,
)
from app.models.schemas import (
    DiagnosticReport,
    Finding,
    Severity,
    SignalType,
    SourceCitation,
)


def _make_report(
    signal_types: list[SignalType],
    findings_with_sources: list[tuple[str, list[str]]] | None = None,
) -> DiagnosticReport:
    findings = []
    if findings_with_sources:
        for title, source_paths in findings_with_sources:
            findings.append(Finding(
                severity=Severity.warning,
                title=title,
                description="desc",
                root_cause="cause",
                remediation="fix",
                source_signals=[SignalType.events],
                sources=[SourceCitation(file_path=p, excerpt="...") for p in source_paths],
            ))
    return DiagnosticReport(
        executive_summary="summary",
        findings=findings,
        signal_types_analyzed=signal_types,
    )


class TestCheckCoverage:
    def test_full_coverage_score_1(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([SignalType.events, SignalType.pod_logs])
        result = check_coverage(report, bundle_types)
        assert result.score == 1.0

    def test_partial_coverage_score_proportional(self):
        bundle_types = {SignalType.events, SignalType.pod_logs, SignalType.cluster_info}
        report = _make_report([SignalType.events])
        result = check_coverage(report, bundle_types)
        assert 0.3 <= result.score <= 0.4

    def test_no_coverage_score_0(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([])
        result = check_coverage(report, bundle_types)
        assert result.score == 0.0

    def test_coverage_issues_list_missing_types(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([SignalType.events])
        result = check_coverage(report, bundle_types)
        assert "pod_logs" in result.issues[0]


class TestCheckCitationAccuracy:
    def test_all_citations_valid(self):
        extracted_files = {"bundle/events.json": b"data", "bundle/logs/pod.log": b"data"}
        report = _make_report(
            [SignalType.events],
            [("issue", ["bundle/events.json", "bundle/logs/pod.log"])],
        )
        result = check_citation_accuracy(report, extracted_files)
        assert result.score == 1.0

    def test_some_citations_invalid(self):
        extracted_files = {"bundle/events.json": b"data"}
        report = _make_report(
            [SignalType.events],
            [("issue", ["bundle/events.json", "bundle/nonexistent.log"])],
        )
        result = check_citation_accuracy(report, extracted_files)
        assert result.score == 0.5

    def test_no_citations_score_1(self):
        report = _make_report([SignalType.events])
        result = check_citation_accuracy(report, {})
        assert result.score == 1.0

    def test_all_citations_invalid(self):
        report = _make_report(
            [SignalType.events],
            [("issue", ["fake/path1.txt", "fake/path2.txt"])],
        )
        result = check_citation_accuracy(report, {})
        assert result.score == 0.0


class TestRunProgrammaticEvals:
    def test_passing_evals(self):
        bundle_types = {SignalType.events}
        extracted_files = {"bundle/events.json": b"data"}
        report = _make_report(
            [SignalType.events],
            [("issue", ["bundle/events.json"])],
        )
        eval_report = run_programmatic_evals(report, bundle_types, extracted_files)
        assert eval_report.passed is True
        assert eval_report.composite_score >= 0.7

    def test_failing_evals(self):
        bundle_types = {SignalType.events, SignalType.pod_logs, SignalType.cluster_info}
        report = _make_report([], [("issue", ["fake/path.txt"])])
        eval_report = run_programmatic_evals(report, bundle_types, {})
        assert eval_report.passed is False


class TestBuildRetryFeedback:
    def test_feedback_contains_score_and_issues(self):
        bundle_types = {SignalType.events, SignalType.pod_logs}
        report = _make_report([SignalType.events])
        eval_report = run_programmatic_evals(report, bundle_types, {})
        feedback = build_retry_feedback(eval_report)
        assert "pod_logs" in feedback
        assert "threshold" in feedback.lower()
