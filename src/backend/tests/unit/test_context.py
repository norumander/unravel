"""Unit tests for context assembler and truncation."""

from app.analysis.context import (
    CHARS_PER_TOKEN,
    assemble_context,
    estimate_tokens,
)
from app.models.schemas import BundleFile, SignalType


def _make_file(path: str, content: str, signal_type: SignalType) -> tuple[BundleFile, bytes]:
    """Helper to create a BundleFile and its content bytes."""
    data = content.encode("utf-8")
    bf = BundleFile(path=path, size_bytes=len(data), signal_type=signal_type)
    return bf, data


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_known_length(self):
        # 400 chars / 4 chars per token = 100 tokens
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_approximation(self):
        text = "Hello, world!"  # 13 chars -> 3 tokens
        assert estimate_tokens(text) == 13 // CHARS_PER_TOKEN


class TestAssembleContextSmallBundle:
    def test_small_bundle_no_truncation(self):
        bf1, data1 = _make_file("bundle/events.json", "event data", SignalType.events)
        bf2, data2 = _make_file("bundle/logs/pod.log", "log data", SignalType.pod_logs)

        classified = {
            SignalType.events: [bf1],
            SignalType.pod_logs: [bf2],
        }
        files = {bf1.path: data1, bf2.path: data2}

        ctx = assemble_context(classified, files)

        assert SignalType.events in ctx.signal_contents
        assert SignalType.pod_logs in ctx.signal_contents
        assert ctx.truncation_notes is None

    def test_content_includes_file_paths(self):
        bf, data = _make_file("bundle/events.json", "event data", SignalType.events)
        classified = {SignalType.events: [bf]}
        files = {bf.path: data}

        ctx = assemble_context(classified, files)

        assert "bundle/events.json" in ctx.signal_contents[SignalType.events]
        assert "event data" in ctx.signal_contents[SignalType.events]

    def test_empty_bundle_no_content(self):
        classified: dict[SignalType, list[BundleFile]] = {}
        files: dict[str, bytes] = {}

        ctx = assemble_context(classified, files)

        assert len(ctx.signal_contents) == 0
        assert ctx.truncation_notes is None

    def test_other_signal_type_excluded(self):
        """Files classified as 'other' should not be included in analysis context."""
        bf, data = _make_file("bundle/version.txt", "v1.0", SignalType.other)
        classified = {SignalType.other: [bf]}
        files = {bf.path: data}

        ctx = assemble_context(classified, files)
        assert SignalType.other not in ctx.signal_contents


class TestAssembleContextTruncation:
    def test_large_bundle_gets_truncated(self):
        # Create content that exceeds the token budget
        budget = 100  # 100 tokens = 400 chars
        large_content = "x" * (budget * CHARS_PER_TOKEN * 2)  # 200 tokens worth

        bf, data = _make_file("bundle/events.json", large_content, SignalType.events)
        classified = {SignalType.events: [bf]}
        files = {bf.path: data}

        ctx = assemble_context(classified, files, token_budget=budget)

        total_tokens = estimate_tokens(ctx.signal_contents.get(SignalType.events, ""))
        # Should be within budget (with some margin for headers)
        assert total_tokens <= budget * 1.1  # 10% tolerance

    def test_truncation_notes_present(self):
        budget = 50
        large_content = "x" * (budget * CHARS_PER_TOKEN * 3)

        bf, data = _make_file("bundle/events.json", large_content, SignalType.events)
        classified = {SignalType.events: [bf]}
        files = {bf.path: data}

        ctx = assemble_context(classified, files, token_budget=budget)
        assert ctx.truncation_notes is not None
        assert "events" in ctx.truncation_notes

    def test_high_priority_preserved_over_low_priority(self):
        budget = 200  # Only room for ~200 tokens

        # Events: high priority, 150 tokens
        events_content = "e" * (150 * CHARS_PER_TOKEN)
        bf_events, data_events = _make_file(
            "bundle/events.json", events_content, SignalType.events
        )

        # Node status: low priority, 150 tokens
        node_content = "n" * (150 * CHARS_PER_TOKEN)
        bf_node, data_node = _make_file(
            "bundle/nodes/worker.json", node_content, SignalType.node_status
        )

        classified = {
            SignalType.events: [bf_events],
            SignalType.node_status: [bf_node],
        }
        files = {bf_events.path: data_events, bf_node.path: data_node}

        ctx = assemble_context(classified, files, token_budget=budget)

        # Events should be fully present
        assert SignalType.events in ctx.signal_contents
        events_tokens = estimate_tokens(ctx.signal_contents[SignalType.events])
        # Events had ~150 tokens of raw content plus header, should be mostly preserved
        assert events_tokens > 100

    def test_lowest_priority_excluded_when_budget_exhausted(self):
        budget = 100

        # Fill budget with events
        events_content = "e" * (budget * CHARS_PER_TOKEN)
        bf_events, data_events = _make_file(
            "bundle/events.json", events_content, SignalType.events
        )

        # Node status won't fit
        node_content = "n" * (50 * CHARS_PER_TOKEN)
        bf_node, data_node = _make_file(
            "bundle/nodes/worker.json", node_content, SignalType.node_status
        )

        classified = {
            SignalType.events: [bf_events],
            SignalType.node_status: [bf_node],
        }
        files = {bf_events.path: data_events, bf_node.path: data_node}

        ctx = assemble_context(classified, files, token_budget=budget)

        assert ctx.truncation_notes is not None
        assert "node_status" in ctx.truncation_notes

    def test_multiple_files_per_type_combined(self):
        bf1, data1 = _make_file("bundle/logs/pod1.log", "log1 data", SignalType.pod_logs)
        bf2, data2 = _make_file("bundle/logs/pod2.log", "log2 data", SignalType.pod_logs)

        classified = {SignalType.pod_logs: [bf1, bf2]}
        files = {bf1.path: data1, bf2.path: data2}

        ctx = assemble_context(classified, files)

        content = ctx.signal_contents[SignalType.pod_logs]
        assert "log1 data" in content
        assert "log2 data" in content

    def test_manifest_built_from_classified(self):
        bf, data = _make_file("bundle/events.json", "data", SignalType.events)
        classified = {SignalType.events: [bf]}
        files = {bf.path: data}

        ctx = assemble_context(classified, files)

        assert ctx.manifest.total_files == 1
        assert ctx.manifest.files[0].path == "bundle/events.json"


class TestAssembleContextEdgeCases:
    def test_zero_budget_excludes_all_signals(self):
        """X-14: A zero token budget should exclude all signal types."""
        bf_events, data_events = _make_file(
            "bundle/events.json", "event data", SignalType.events
        )
        bf_logs, data_logs = _make_file(
            "bundle/logs/pod.log", "log data", SignalType.pod_logs
        )
        bf_cluster, data_cluster = _make_file(
            "bundle/cluster/info.json", "cluster info", SignalType.cluster_info
        )

        classified = {
            SignalType.events: [bf_events],
            SignalType.pod_logs: [bf_logs],
            SignalType.cluster_info: [bf_cluster],
        }
        files = {
            bf_events.path: data_events,
            bf_logs.path: data_logs,
            bf_cluster.path: data_cluster,
        }

        ctx = assemble_context(classified, files, token_budget=0)

        assert len(ctx.signal_contents) == 0
        assert ctx.truncation_notes is not None
        for signal_type in [SignalType.events, SignalType.pod_logs, SignalType.cluster_info]:
            assert signal_type.value in ctx.truncation_notes

    def test_truncation_preserves_tail_content(self):
        """X-16: Truncation should keep the tail (most recent lines), not the head."""
        lines = [f"line {i}" for i in range(1, 101)]
        content = "\n".join(lines)
        bf, data = _make_file("bundle/events.json", content, SignalType.events)

        classified = {SignalType.events: [bf]}
        files = {bf.path: data}

        # Use a tiny budget that forces truncation
        budget = 20  # 20 tokens = 80 chars — only room for a few lines
        ctx = assemble_context(classified, files, token_budget=budget)

        result = ctx.signal_contents.get(SignalType.events, "")
        assert "line 100" in result
        assert "line 1\n" not in result

    def test_binary_content_decoded_with_replacement(self):
        """X-17: Invalid UTF-8 bytes should be decoded with the replacement character."""
        raw_bytes = b"\xff\xfe invalid utf-8 bytes \xff"
        bf = BundleFile(
            path="bundle/events.bin",
            size_bytes=len(raw_bytes),
            signal_type=SignalType.events,
        )

        classified = {SignalType.events: [bf]}
        files = {bf.path: raw_bytes}

        ctx = assemble_context(classified, files)

        result = ctx.signal_contents[SignalType.events]
        assert "\ufffd" in result

    def test_missing_file_in_files_dict_skipped(self):
        """X-18: A classified file whose path is absent from files dict should be skipped."""
        bf_present, data_present = _make_file(
            "bundle/events.json", "event data", SignalType.events
        )
        bf_missing = BundleFile(
            path="bundle/events_missing.json",
            size_bytes=100,
            signal_type=SignalType.events,
        )

        classified = {SignalType.events: [bf_present, bf_missing]}
        files = {bf_present.path: data_present}
        # bf_missing.path is intentionally NOT in files

        ctx = assemble_context(classified, files)

        # Should not raise; present file content should still appear
        result = ctx.signal_contents[SignalType.events]
        assert "event data" in result
        # The missing file should simply be absent from the output
        assert "events_missing.json" not in result
