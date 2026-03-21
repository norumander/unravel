"""Tests for session persistence data models."""

import pytest
from datetime import datetime, UTC
from app.models.schemas import (
    FindingSummary,
    BundleMetadata,
    LLMMetaSummary,
    SessionSummary,
)


class TestFindingSummary:
    def test_create_with_valid_severity(self):
        f = FindingSummary(severity="critical", title="CrashLoopBackOff")
        assert f.severity == "critical"
        assert f.title == "CrashLoopBackOff"

    def test_rejects_invalid_severity(self):
        with pytest.raises(ValueError):
            FindingSummary(severity="unknown", title="test")


class TestBundleMetadata:
    def test_defaults_to_empty(self):
        meta = BundleMetadata()
        assert meta.cluster is None
        assert meta.namespaces == []
        assert meta.k8s_version is None
        assert meta.node_count is None

    def test_with_all_fields(self):
        meta = BundleMetadata(
            cluster="prod-east-1",
            namespaces=["default", "kube-system"],
            k8s_version="v1.28.4",
            node_count=3,
        )
        assert meta.cluster == "prod-east-1"
        assert len(meta.namespaces) == 2


class TestLLMMetaSummary:
    def test_create(self):
        m = LLMMetaSummary(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            input_tokens=1000,
            output_tokens=500,
            latency_ms=3200,
        )
        assert m.provider == "anthropic"
        assert m.latency_ms == 3200


class TestSessionSummary:
    def test_create_completed_session(self):
        s = SessionSummary(
            id="abc-123",
            bundle_name="test.tar.gz",
            file_size=1024,
            timestamp=datetime.now(UTC).isoformat(),
            status="completed",
        )
        assert s.status == "completed"
        assert s.notes == ""
        assert s.tags == []
        assert s.findings_summary == []

    def test_rejects_invalid_status(self):
        with pytest.raises(ValueError):
            SessionSummary(
                id="x",
                bundle_name="t.tar.gz",
                file_size=0,
                timestamp=datetime.now(UTC).isoformat(),
                status="invalid",
            )

    def test_serialization_roundtrip(self):
        s = SessionSummary(
            id="abc-123",
            bundle_name="test.tar.gz",
            file_size=1024,
            timestamp=datetime.now(UTC).isoformat(),
            status="completed",
            bundle_metadata=BundleMetadata(cluster="prod"),
            findings_summary=[
                FindingSummary(severity="critical", title="OOM")
            ],
        )
        data = s.model_dump()
        restored = SessionSummary(**data)
        assert restored.id == s.id
        assert restored.bundle_metadata.cluster == "prod"
