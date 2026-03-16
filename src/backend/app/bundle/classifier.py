"""Signal classifier — classifies bundle files by path patterns into signal types."""

import re

from app.models.schemas import BundleFile, BundleManifest, SignalType

# Path patterns for each signal type, ordered by specificity.
# Patterns are matched against the normalized file path.
_SIGNAL_PATTERNS: list[tuple[SignalType, re.Pattern[str]]] = [
    (SignalType.events, re.compile(r"(^|/)events\.json$|(^|/)events/")),
    (SignalType.pod_logs, re.compile(r"(^|/)(pod-?logs|logs)/")),
    (SignalType.cluster_info, re.compile(r"(^|/)cluster-info/")),
    (SignalType.resource_definitions, re.compile(r"(^|/)cluster-resources/")),
    (SignalType.node_status, re.compile(r"(^|/)(nodes/|node[_-]list)")),
]


def classify_file(path: str) -> SignalType:
    """Classify a single file path into a signal type.

    Classification is path-based only — file content is never inspected.
    """
    for signal_type, pattern in _SIGNAL_PATTERNS:
        if pattern.search(path):
            return signal_type
    return SignalType.other


def classify_files(manifest: BundleManifest) -> dict[SignalType, list[BundleFile]]:
    """Classify all files in a manifest into signal types.

    Returns a dict mapping each signal type to the list of files classified under it.
    Updates the signal_type field on each BundleFile in place.
    """
    classified: dict[SignalType, list[BundleFile]] = {st: [] for st in SignalType}

    for bundle_file in manifest.files:
        signal_type = classify_file(bundle_file.path)
        bundle_file.signal_type = signal_type
        classified[signal_type].append(bundle_file)

    return classified
