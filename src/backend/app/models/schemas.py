"""Pydantic models and enums for the Unravel application."""

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """Classification of bundle file signal types."""

    pod_logs = "pod_logs"
    cluster_info = "cluster_info"
    resource_definitions = "resource_definitions"
    events = "events"
    node_status = "node_status"
    other = "other"


class Severity(str, Enum):
    """Severity level for diagnostic findings."""

    critical = "critical"
    warning = "warning"
    info = "info"


class BundleFile(BaseModel):
    """A single file within a support bundle."""

    path: str
    size_bytes: int
    signal_type: SignalType


class BundleManifest(BaseModel):
    """Manifest of all files in an uploaded support bundle."""

    total_files: int
    total_size_bytes: int
    files: list[BundleFile]


class SourceCitation(BaseModel):
    """A reference to a specific file and excerpt supporting a finding."""

    file_path: str
    excerpt: str


class Finding(BaseModel):
    """A single diagnostic finding from the analysis."""

    severity: Severity
    title: str
    description: str
    root_cause: str
    remediation: str
    source_signals: list[SignalType]
    sources: list[SourceCitation] | None = None


class TimelineEvent(BaseModel):
    """A timestamped event extracted from the bundle for timeline visualization."""

    timestamp: str
    title: str
    description: str
    severity: Severity
    source: str


class DiagnosticReport(BaseModel):
    """Structured diagnostic report produced by LLM analysis."""

    executive_summary: str
    findings: list[Finding]
    signal_types_analyzed: list[SignalType]
    truncation_notes: str | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    eval_scores: dict[str, float] | None = None


class ToolCall(BaseModel):
    """A tool call made by the LLM during chat."""

    name: str
    arguments: dict
    result: str | None = None


class ChatMessage(BaseModel):
    """A message in the chat conversation."""

    role: str
    content: str
    tool_call: ToolCall | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class FindingSummary(BaseModel):
    """Lightweight finding for session index — severity + title only."""

    severity: Literal["critical", "warning", "info"]
    title: str


class BundleMetadata(BaseModel):
    """Auto-extracted metadata from the support bundle."""

    cluster: str | None = None
    namespaces: list[str] = Field(default_factory=list)
    k8s_version: str | None = None
    node_count: int | None = None


class LLMMetaSummary(BaseModel):
    """LLM call metadata for session persistence."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class SessionSummary(BaseModel):
    """Session index entry — lightweight data for the dashboard table."""

    id: str
    bundle_name: str
    file_size: int
    timestamp: str
    status: Literal["completed", "error"]
    bundle_metadata: BundleMetadata = Field(default_factory=BundleMetadata)
    findings_summary: list[FindingSummary] = Field(default_factory=list)
    llm_meta: LLMMetaSummary | None = None
    eval_score: float | None = None
    notes: str = ""
    tags: list[str] = Field(default_factory=list)


class AnalysisContext(BaseModel):
    """Assembled context for LLM analysis, after classification and truncation."""

    signal_contents: dict[SignalType, str]
    truncation_notes: str | None = None
    manifest: BundleManifest


class Session(BaseModel):
    """In-memory session holding all data for a single bundle analysis."""

    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    bundle_manifest: BundleManifest
    extracted_files: dict[str, bytes]
    classified_signals: dict[SignalType, list[BundleFile]]
    report: DiagnosticReport | None = None
    analyzing: bool = False
    chat_history: list[ChatMessage] = Field(default_factory=list)
    chroma_collection_name: str | None = None
