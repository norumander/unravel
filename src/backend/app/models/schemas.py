"""Pydantic models and enums for the Unravel application."""

from datetime import UTC, datetime
from enum import Enum

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


class Finding(BaseModel):
    """A single diagnostic finding from the analysis."""

    severity: Severity
    title: str
    description: str
    root_cause: str
    remediation: str
    source_signals: list[SignalType]


class DiagnosticReport(BaseModel):
    """Structured diagnostic report produced by LLM analysis."""

    executive_summary: str
    findings: list[Finding]
    signal_types_analyzed: list[SignalType]
    truncation_notes: str | None = None


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
    chat_history: list[ChatMessage] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
