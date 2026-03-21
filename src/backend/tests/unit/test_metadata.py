"""Tests for bundle metadata extraction."""

import json
import pytest
from app.sessions.metadata import extract_bundle_metadata
from app.models.schemas import BundleMetadata


class TestExtractBundleMetadata:
    def test_extracts_k8s_version(self):
        files = {
            "cluster-resources/server-version.json": json.dumps(
                {"major": "1", "minor": "28", "gitVersion": "v1.28.4"}
            ).encode()
        }
        meta = extract_bundle_metadata(files)
        assert meta.k8s_version == "v1.28.4"

    def test_extracts_node_count(self):
        files = {
            "cluster-resources/nodes.json": json.dumps(
                {"items": [{"metadata": {"name": "node1"}}, {"metadata": {"name": "node2"}}]}
            ).encode()
        }
        meta = extract_bundle_metadata(files)
        assert meta.node_count == 2

    def test_extracts_namespaces_from_paths(self):
        files = {
            "cluster-resources/pods/default.json": b"{}",
            "cluster-resources/pods/kube-system.json": b"{}",
            "cluster-resources/pods/app.json": b"{}",
        }
        meta = extract_bundle_metadata(files)
        assert sorted(meta.namespaces) == ["app", "default", "kube-system"]

    def test_cluster_name_is_none_by_default(self):
        files = {
            "cluster-info/cluster_version.json": json.dumps(
                {"status": {"desired": {"version": "4.12"}}}
            ).encode(),
        }
        meta = extract_bundle_metadata(files)
        assert meta.cluster is None

    def test_handles_missing_files_gracefully(self):
        meta = extract_bundle_metadata({})
        assert meta.k8s_version is None
        assert meta.node_count is None
        assert meta.namespaces == []

    def test_handles_malformed_json(self):
        files = {
            "cluster-resources/server-version.json": b"not json",
            "cluster-resources/nodes.json": b"{invalid",
        }
        meta = extract_bundle_metadata(files)
        assert meta.k8s_version is None
        assert meta.node_count is None

    def test_returns_bundle_metadata_type(self):
        meta = extract_bundle_metadata({})
        assert isinstance(meta, BundleMetadata)
