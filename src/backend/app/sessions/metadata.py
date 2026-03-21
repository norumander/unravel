"""Extract structured metadata from support bundle files."""

import json
import logging
import re

from app.models.schemas import BundleMetadata

logger = logging.getLogger(__name__)

# Pattern to match namespace-scoped resource files like:
# cluster-resources/pods/default.json
# cluster-resources/deployments/kube-system.json
_NAMESPACE_PATTERN = re.compile(
    r"cluster-resources/[^/]+/([a-z0-9][-a-z0-9]*)\.json$"
)


def extract_bundle_metadata(
    extracted_files: dict[str, bytes],
) -> BundleMetadata:
    """Extract cluster metadata from bundle files.

    Best-effort extraction — returns defaults for anything missing or
    malformed. Never raises on bad data.
    """
    k8s_version = _extract_k8s_version(extracted_files)
    node_count = _extract_node_count(extracted_files)
    namespaces = _extract_namespaces(extracted_files)

    return BundleMetadata(
        cluster=None,  # No reliable source in standard bundles
        k8s_version=k8s_version,
        node_count=node_count,
        namespaces=sorted(namespaces),
    )


def _extract_k8s_version(files: dict[str, bytes]) -> str | None:
    for path, content in files.items():
        if path.endswith("server-version.json"):
            try:
                data = json.loads(content)
                return data.get("gitVersion")
            except (json.JSONDecodeError, AttributeError):
                return None
    return None


def _extract_node_count(files: dict[str, bytes]) -> int | None:
    for path, content in files.items():
        if path.endswith("nodes.json") and "cluster-resources" in path:
            try:
                data = json.loads(content)
                items = data.get("items", [])
                return len(items)
            except (json.JSONDecodeError, AttributeError):
                return None
    return None


def _extract_namespaces(files: dict[str, bytes]) -> list[str]:
    namespaces: set[str] = set()
    for path in files:
        match = _NAMESPACE_PATTERN.search(path)
        if match:
            ns = match.group(1)
            if ns not in ("cluster", "node", "global"):
                namespaces.add(ns)
    return list(namespaces)
