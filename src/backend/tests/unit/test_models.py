"""Unit tests for Pydantic models and enums."""

import json
from datetime import datetime

from app.models.schemas import (
    AnalysisContext,
    BundleFile,
    BundleManifest,
    ChatMessage,
    DiagnosticReport,
    Finding,
    Session,
    Severity,
    SignalType,
    SourceCitation,
    ToolCall,
)


class TestSignalType:
    def test_values_are_lowercase_strings(self):
        for member in SignalType:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_serializes_to_string(self):
        assert SignalType.pod_logs.value == "pod_logs"
        assert SignalType.events.value == "events"
        assert SignalType.other.value == "other"


class TestSeverity:
    def test_values_are_lowercase_strings(self):
        for member in Severity:
            assert member.value == member.value.lower()
            assert isinstance(member.value, str)

    def test_serializes_to_string(self):
        assert Severity.critical.value == "critical"
        assert Severity.warning.value == "warning"
        assert Severity.info.value == "info"


class TestBundleFile:
    def test_create_and_serialize(self):
        bf = BundleFile(path="logs/pod.log", size_bytes=1024, signal_type=SignalType.pod_logs)
        data = bf.model_dump()
        assert data["path"] == "logs/pod.log"
        assert data["size_bytes"] == 1024
        assert data["signal_type"] == "pod_logs"

    def test_json_roundtrip(self):
        bf = BundleFile(path="events.json", size_bytes=512, signal_type=SignalType.events)
        json_str = bf.model_dump_json()
        restored = BundleFile.model_validate_json(json_str)
        assert restored == bf


class TestBundleManifest:
    def test_create_and_serialize(self):
        files = [
            BundleFile(path="a.log", size_bytes=100, signal_type=SignalType.pod_logs),
            BundleFile(path="b.yaml", size_bytes=200, signal_type=SignalType.resource_definitions),
        ]
        manifest = BundleManifest(total_files=2, total_size_bytes=300, files=files)
        data = manifest.model_dump()
        assert data["total_files"] == 2
        assert len(data["files"]) == 2

    def test_json_roundtrip(self):
        files = [BundleFile(path="x.log", size_bytes=50, signal_type=SignalType.other)]
        manifest = BundleManifest(total_files=1, total_size_bytes=50, files=files)
        restored = BundleManifest.model_validate_json(manifest.model_dump_json())
        assert restored == manifest


class TestFinding:
    def test_create_with_all_fields(self):
        f = Finding(
            severity=Severity.critical,
            title="CrashLoopBackOff",
            description="Pod is crash-looping",
            root_cause="OOM kill due to memory limit",
            remediation="Increase memory limit to 512Mi",
            source_signals=[SignalType.pod_logs, SignalType.events],
        )
        data = f.model_dump()
        assert data["severity"] == "critical"
        assert data["source_signals"] == ["pod_logs", "events"]

    def test_create_with_sources(self):
        f = Finding(
            severity=Severity.critical,
            title="OOM",
            description="Out of memory",
            root_cause="Memory limit too low",
            remediation="Increase limits",
            source_signals=[SignalType.pod_logs],
            sources=[
                SourceCitation(file_path="logs/pod.log", excerpt="OOMKilled"),
                SourceCitation(file_path="events.json", excerpt="Memory cgroup out of memory"),
            ],
        )
        data = f.model_dump()
        assert len(data["sources"]) == 2
        assert data["sources"][0]["file_path"] == "logs/pod.log"

    def test_sources_optional(self):
        f = Finding(
            severity=Severity.info,
            title="Test",
            description="Desc",
            root_cause="Cause",
            remediation="Fix",
            source_signals=[SignalType.events],
        )
        assert f.sources is None

    def test_json_roundtrip(self):
        f = Finding(
            severity=Severity.warning,
            title="High restart count",
            description="Pod has restarted 10 times",
            root_cause="Liveness probe failure",
            remediation="Adjust probe thresholds",
            source_signals=[SignalType.pod_logs],
        )
        restored = Finding.model_validate_json(f.model_dump_json())
        assert restored == f


class TestDiagnosticReport:
    def test_create_and_serialize(self):
        report = DiagnosticReport(
            executive_summary="Cluster has critical issues.",
            findings=[
                Finding(
                    severity=Severity.critical,
                    title="OOM",
                    description="Out of memory",
                    root_cause="Memory limit too low",
                    remediation="Increase limits",
                    source_signals=[SignalType.pod_logs],
                )
            ],
            signal_types_analyzed=[SignalType.pod_logs, SignalType.events],
            truncation_notes=None,
        )
        data = report.model_dump()
        assert data["executive_summary"] == "Cluster has critical issues."
        assert len(data["findings"]) == 1
        assert data["truncation_notes"] is None

    def test_with_truncation_notes(self):
        report = DiagnosticReport(
            executive_summary="Summary",
            findings=[],
            signal_types_analyzed=[],
            truncation_notes="node_status truncated by 50%",
        )
        data = json.loads(report.model_dump_json())
        assert data["truncation_notes"] == "node_status truncated by 50%"

    def test_json_roundtrip(self):
        report = DiagnosticReport(
            executive_summary="All good",
            findings=[],
            signal_types_analyzed=[SignalType.cluster_info],
        )
        restored = DiagnosticReport.model_validate_json(report.model_dump_json())
        assert restored == report


class TestToolCall:
    def test_create_and_serialize(self):
        tc = ToolCall(
            name="get_file_contents",
            arguments={"file_path": "logs/pod.log"},
            result="log content here",
        )
        data = tc.model_dump()
        assert data["name"] == "get_file_contents"
        assert data["arguments"]["file_path"] == "logs/pod.log"

    def test_result_optional(self):
        tc = ToolCall(name="get_file_contents", arguments={"file_path": "x.log"})
        assert tc.result is None

    def test_json_roundtrip(self):
        tc = ToolCall(name="get_file_contents", arguments={"file_path": "a.log"}, result="data")
        restored = ToolCall.model_validate_json(tc.model_dump_json())
        assert restored == tc


class TestChatMessage:
    def test_create_user_message(self):
        msg = ChatMessage(role="user", content="What's wrong with the pod?")
        assert msg.role == "user"
        assert msg.tool_call is None
        assert isinstance(msg.timestamp, datetime)

    def test_create_tool_message(self):
        tc = ToolCall(name="get_file_contents", arguments={"file_path": "a.log"}, result="data")
        msg = ChatMessage(role="tool", content="data", tool_call=tc)
        assert msg.tool_call is not None
        assert msg.tool_call.name == "get_file_contents"

    def test_json_roundtrip(self):
        msg = ChatMessage(role="assistant", content="The pod is crash-looping.")
        restored = ChatMessage.model_validate_json(msg.model_dump_json())
        assert restored.role == msg.role
        assert restored.content == msg.content


class TestAnalysisContext:
    def test_create_and_serialize(self):
        manifest = BundleManifest(
            total_files=1,
            total_size_bytes=100,
            files=[BundleFile(path="a.log", size_bytes=100, signal_type=SignalType.pod_logs)],
        )
        ctx = AnalysisContext(
            signal_contents={SignalType.pod_logs: "log data here"},
            truncation_notes=None,
            manifest=manifest,
        )
        data = ctx.model_dump()
        assert "pod_logs" in data["signal_contents"]

    def test_json_roundtrip(self):
        manifest = BundleManifest(total_files=0, total_size_bytes=0, files=[])
        ctx = AnalysisContext(
            signal_contents={},
            manifest=manifest,
        )
        restored = AnalysisContext.model_validate_json(ctx.model_dump_json())
        assert restored == ctx


class TestSession:
    def test_create_minimal(self):
        manifest = BundleManifest(total_files=0, total_size_bytes=0, files=[])
        session = Session(
            session_id="test-123",
            bundle_manifest=manifest,
            extracted_files={},
            classified_signals={},
        )
        assert session.session_id == "test-123"
        assert session.report is None
        assert session.chat_history == []
        assert isinstance(session.created_at, datetime)

    def test_session_with_data(self):
        bf = BundleFile(path="a.log", size_bytes=100, signal_type=SignalType.pod_logs)
        manifest = BundleManifest(total_files=1, total_size_bytes=100, files=[bf])
        session = Session(
            session_id="test-456",
            bundle_manifest=manifest,
            extracted_files={"a.log": b"log content"},
            classified_signals={SignalType.pod_logs: [bf]},
        )
        assert len(session.extracted_files) == 1
        assert SignalType.pod_logs in session.classified_signals
