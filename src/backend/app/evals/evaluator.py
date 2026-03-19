"""Programmatic quality evaluator — scores diagnostic reports on coverage and citation accuracy."""

import logging
import os
from dataclasses import dataclass, field

from app.models.schemas import DiagnosticReport, SignalType

logger = logging.getLogger(__name__)

EVAL_THRESHOLD = float(os.environ.get("EVAL_THRESHOLD", "0.7"))


@dataclass
class EvalResult:
    dimension: str
    score: float
    issues: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    results: list[EvalResult]
    composite_score: float
    passed: bool

    def to_dict(self) -> dict:
        return {
            "composite_score": round(self.composite_score, 3),
            "passed": self.passed,
            "dimensions": {
                r.dimension: {"score": round(r.score, 3), "issues": r.issues}
                for r in self.results
            },
        }


def check_coverage(report: DiagnosticReport, bundle_signal_types: set[SignalType]) -> EvalResult:
    if not bundle_signal_types:
        return EvalResult(dimension="coverage", score=1.0)

    analyzed = set(report.signal_types_analyzed)
    relevant_types = bundle_signal_types - {SignalType.other}
    if not relevant_types:
        return EvalResult(dimension="coverage", score=1.0)

    covered = analyzed & relevant_types
    score = len(covered) / len(relevant_types)

    issues = []
    missing = relevant_types - covered
    if missing:
        issues.append(f"Signal types not analyzed: {', '.join(st.value for st in missing)}")

    return EvalResult(dimension="coverage", score=score, issues=issues)


def check_citation_accuracy(report: DiagnosticReport, extracted_files: dict[str, bytes]) -> EvalResult:
    all_citations = []
    for finding in report.findings:
        if finding.sources:
            all_citations.extend(finding.sources)

    if not all_citations:
        return EvalResult(dimension="citation_accuracy", score=1.0)

    valid = sum(1 for c in all_citations if c.file_path in extracted_files)
    score = valid / len(all_citations)

    issues = []
    invalid_paths = [c.file_path for c in all_citations if c.file_path not in extracted_files]
    if invalid_paths:
        issues.append(f"Invalid file paths in citations: {', '.join(invalid_paths[:5])}")

    return EvalResult(dimension="citation_accuracy", score=score, issues=issues)


def run_programmatic_evals(
    report: DiagnosticReport,
    bundle_signal_types: set[SignalType],
    extracted_files: dict[str, bytes],
) -> EvalReport:
    coverage = check_coverage(report, bundle_signal_types)
    citation = check_citation_accuracy(report, extracted_files)

    results = [coverage, citation]
    composite = sum(r.score for r in results) / len(results)
    passed = composite >= EVAL_THRESHOLD

    return EvalReport(results=results, composite_score=composite, passed=passed)


def build_retry_feedback(eval_report: EvalReport) -> str:
    parts = [
        f"Your previous report scored {eval_report.composite_score:.2f} "
        f"(threshold: {EVAL_THRESHOLD}). Specific issues:"
    ]
    for result in eval_report.results:
        if result.issues:
            parts.append(f"- {result.dimension}: {'; '.join(result.issues)}")

    parts.append(
        "\nPlease improve your analysis. Ensure you analyze ALL signal types "
        "present in the bundle and cite actual file paths from the manifest."
    )
    return "\n".join(parts)
