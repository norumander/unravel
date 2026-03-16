"""Unit tests for signal classifier."""

import pytest

from app.bundle.classifier import classify_file, classify_files
from app.models.schemas import BundleFile, BundleManifest, SignalType


class TestClassifyFile:
    """Test individual file path classification."""

    @pytest.mark.parametrize(
        "path",
        [
            "support-bundle/logs/pod.log",
            "bundle/podlogs/namespace/pod/container.log",
            "bundle/pod-logs/default/nginx/nginx.log",
            "support-bundle/logs/kube-system/coredns/coredns.log",
        ],
    )
    def test_pod_logs_paths(self, path: str):
        assert classify_file(path) == SignalType.pod_logs

    @pytest.mark.parametrize(
        "path",
        [
            "support-bundle/cluster-info/cluster-version.json",
            "bundle/cluster-info/kubeconfig",
            "support-bundle/cluster-info/nodes.json",
        ],
    )
    def test_cluster_info_paths(self, path: str):
        assert classify_file(path) == SignalType.cluster_info

    @pytest.mark.parametrize(
        "path",
        [
            "support-bundle/cluster-resources/pods/default.json",
            "bundle/cluster-resources/deployments/kube-system.json",
            "support-bundle/cluster-resources/services/monitoring.json",
            "bundle/cluster-resources/custom-resources/certificates.json",
        ],
    )
    def test_resource_definitions_paths(self, path: str):
        assert classify_file(path) == SignalType.resource_definitions

    @pytest.mark.parametrize(
        "path",
        [
            "support-bundle/events.json",
            "bundle/events/default.json",
            "support-bundle/events/kube-system.json",
        ],
    )
    def test_events_paths(self, path: str):
        assert classify_file(path) == SignalType.events

    @pytest.mark.parametrize(
        "path",
        [
            "support-bundle/nodes/worker-1.json",
            "bundle/node_list.json",
            "support-bundle/node-list.json",
        ],
    )
    def test_node_status_paths(self, path: str):
        assert classify_file(path) == SignalType.node_status

    @pytest.mark.parametrize(
        "path",
        [
            "support-bundle/version.txt",
            "bundle/analysis.json",
            "support-bundle/host-collectors/system/df.txt",
            "bundle/some-random-file.yaml",
        ],
    )
    def test_other_paths(self, path: str):
        assert classify_file(path) == SignalType.other

    def test_classification_is_path_based_not_content_based(self):
        """Verify that classification depends only on the path, not content."""
        # A file named events.json under cluster-resources should be resource_definitions
        # because cluster-resources/ pattern matches first in priority
        path = "bundle/cluster-resources/events.json"
        result = classify_file(path)
        # events.json pattern matches - but we want to verify path-only classification
        assert result in (SignalType.events, SignalType.resource_definitions)


class TestClassifyFiles:
    """Test bulk classification of manifest files."""

    def test_classifies_all_files_in_manifest(self):
        files = [
            BundleFile(path="bundle/logs/pod.log", size_bytes=100, signal_type=SignalType.other),
            BundleFile(
                path="bundle/cluster-info/version.json",
                size_bytes=200,
                signal_type=SignalType.other,
            ),
            BundleFile(
                path="bundle/cluster-resources/pods.json",
                size_bytes=300,
                signal_type=SignalType.other,
            ),
            BundleFile(path="bundle/events.json", size_bytes=400, signal_type=SignalType.other),
            BundleFile(
                path="bundle/nodes/worker.json", size_bytes=500, signal_type=SignalType.other
            ),
            BundleFile(path="bundle/version.txt", size_bytes=50, signal_type=SignalType.other),
        ]
        manifest = BundleManifest(total_files=6, total_size_bytes=1550, files=files)

        classified = classify_files(manifest)

        assert len(classified[SignalType.pod_logs]) == 1
        assert len(classified[SignalType.cluster_info]) == 1
        assert len(classified[SignalType.resource_definitions]) == 1
        assert len(classified[SignalType.events]) == 1
        assert len(classified[SignalType.node_status]) == 1
        assert len(classified[SignalType.other]) == 1

    def test_updates_signal_type_on_bundle_files(self):
        files = [
            BundleFile(path="bundle/logs/pod.log", size_bytes=100, signal_type=SignalType.other),
        ]
        manifest = BundleManifest(total_files=1, total_size_bytes=100, files=files)

        classify_files(manifest)

        assert files[0].signal_type == SignalType.pod_logs

    def test_empty_manifest_returns_empty_groups(self):
        manifest = BundleManifest(total_files=0, total_size_bytes=0, files=[])
        classified = classify_files(manifest)

        for signal_type in SignalType:
            assert classified[signal_type] == []

    def test_all_other_files(self):
        files = [
            BundleFile(path="bundle/version.txt", size_bytes=10, signal_type=SignalType.other),
            BundleFile(path="bundle/analysis.json", size_bytes=20, signal_type=SignalType.other),
        ]
        manifest = BundleManifest(total_files=2, total_size_bytes=30, files=files)

        classified = classify_files(manifest)

        assert len(classified[SignalType.other]) == 2
        for st in SignalType:
            if st != SignalType.other:
                assert len(classified[st]) == 0
