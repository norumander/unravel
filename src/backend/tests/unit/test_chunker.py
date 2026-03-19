"""Unit tests for content-type-aware chunker."""

import json

from app.bundle.chunker import Chunk, chunk_file
from app.models.schemas import SignalType


class TestFixedSizeChunking:
    def test_small_file_single_chunk(self):
        content = "short content"
        chunks = chunk_file("bundle/info.txt", content, SignalType.cluster_info)
        assert len(chunks) == 1
        assert chunks[0].text == content
        assert chunks[0].file_path == "bundle/info.txt"
        assert chunks[0].signal_type == SignalType.cluster_info
        assert chunks[0].chunk_index == 0

    def test_large_file_multiple_chunks(self):
        content = "x" * 5000
        chunks = chunk_file("bundle/info.txt", content, SignalType.cluster_info)
        assert len(chunks) >= 2
        combined = "".join(c.text for c in chunks)
        assert len(combined) >= len(content)

    def test_chunk_overlap(self):
        content = "x" * 5000
        chunks = chunk_file("bundle/info.txt", content, SignalType.cluster_info)
        if len(chunks) >= 2:
            first_end = chunks[0].char_end
            second_start = chunks[1].char_start
            assert second_start < first_end

    def test_empty_content_returns_empty(self):
        chunks = chunk_file("bundle/empty.txt", "", SignalType.other)
        assert len(chunks) == 0

    def test_chunk_metadata_correct(self):
        content = "some data"
        chunks = chunk_file("bundle/data.txt", content, SignalType.node_status)
        assert all(c.signal_type == SignalType.node_status for c in chunks)
        assert all(c.file_path == "bundle/data.txt" for c in chunks)
        for i, c in enumerate(chunks):
            assert c.chunk_index == i


class TestJsonEventChunking:
    def test_json_array_one_chunk_per_element(self):
        events = [
            {"type": "Warning", "reason": "BackOff", "message": "Back-off restarting"},
            {"type": "Normal", "reason": "Scheduled", "message": "Assigned to node"},
        ]
        content = json.dumps(events)
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) == 2

    def test_json_object_with_items_key(self):
        data = {"items": [{"kind": "Event", "message": "OOM"}, {"kind": "Event", "message": "OK"}]}
        content = json.dumps(data)
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) == 2

    def test_invalid_json_falls_back_to_fixed_size(self):
        content = "this is not json {"
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) >= 1

    def test_single_event_single_chunk(self):
        content = json.dumps([{"type": "Warning", "message": "test"}])
        chunks = chunk_file("bundle/events.json", content, SignalType.events)
        assert len(chunks) == 1


class TestYamlResourceChunking:
    def test_multi_document_yaml(self):
        content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: pod-a\n---\napiVersion: v1\nkind: Service\nmetadata:\n  name: svc-b\n---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: deploy-c"
        chunks = chunk_file("bundle/cluster-resources/pods.yaml", content, SignalType.resource_definitions)
        assert len(chunks) == 3

    def test_single_document_yaml(self):
        content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: pod-a"
        chunks = chunk_file("bundle/cluster-resources/pods.yaml", content, SignalType.resource_definitions)
        assert len(chunks) == 1

    def test_empty_documents_skipped(self):
        content = "---\napiVersion: v1\nkind: Pod\n---\n---\napiVersion: v1\nkind: Service"
        chunks = chunk_file("bundle/cluster-resources/pods.yaml", content, SignalType.resource_definitions)
        assert len(chunks) == 2


class TestLogChunking:
    def test_log_lines_grouped(self):
        lines = [f"2024-01-15T14:00:{i:02d}Z log message {i}" for i in range(60)]
        content = "\n".join(lines)
        chunks = chunk_file("bundle/logs/pod.log", content, SignalType.pod_logs)
        assert len(chunks) >= 1
        for c in chunks:
            assert "\n" in c.text or len(c.text) < 100

    def test_non_timestamped_logs_fall_back(self):
        content = "\n".join([f"plain log line {i}" for i in range(100)])
        chunks = chunk_file("bundle/logs/pod.log", content, SignalType.pod_logs)
        assert len(chunks) >= 1
