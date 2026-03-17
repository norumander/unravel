"""Context assembler — assembles classified bundle content for LLM analysis with truncation."""

from app.models.schemas import (
    AnalysisContext,
    BundleFile,
    BundleManifest,
    SignalType,
)

DEFAULT_TOKEN_BUDGET = 100_000

# Approximate token estimation: 1 token ≈ 4 characters
CHARS_PER_TOKEN = 4

# Priority order for signal types (highest priority first).
# When truncation is needed, lower-priority types are truncated first.
SIGNAL_PRIORITY = [
    SignalType.events,
    SignalType.pod_logs,
    SignalType.cluster_info,
    SignalType.resource_definitions,
    SignalType.node_status,
]


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string."""
    return len(text) // CHARS_PER_TOKEN


def _truncate_content(content: str, max_tokens: int) -> str:
    """Truncate content to fit within a token budget, preserving the most recent lines."""
    if estimate_tokens(content) <= max_tokens:
        return content

    max_chars = max_tokens * CHARS_PER_TOKEN
    # Keep the end of the content (most recent entries)
    truncated = content[-max_chars:]

    # Clean up: start from the first complete line
    first_newline = truncated.find("\n")
    if first_newline != -1 and first_newline < len(truncated) - 1:
        truncated = truncated[first_newline + 1 :]

    return truncated


def assemble_context(
    classified: dict[SignalType, list[BundleFile]],
    files: dict[str, bytes],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> AnalysisContext:
    """Assemble classified bundle content into an AnalysisContext for LLM analysis.

    Applies priority-based truncation when total content exceeds the token budget.
    Priority: events > pod_logs > cluster_info > resource_definitions > node_status.
    Within each type, preserves the most recent content (end of file).
    """
    # Build raw content per signal type
    raw_contents: dict[SignalType, str] = {}
    for signal_type in SIGNAL_PRIORITY:
        signal_files = classified.get(signal_type, [])
        if not signal_files:
            continue

        parts = []
        for bf in signal_files:
            file_content = files.get(bf.path)
            if file_content is None:
                continue
            text = file_content.decode("utf-8", errors="replace")
            parts.append(f"--- {bf.path} ---\n{text}")

        if parts:
            raw_contents[signal_type] = "\n\n".join(parts)

    # Calculate total tokens
    total_tokens = sum(estimate_tokens(c) for c in raw_contents.values())

    # No truncation needed
    if total_tokens <= token_budget:
        manifest = _build_manifest(classified)
        return AnalysisContext(
            signal_contents=raw_contents,
            truncation_notes=None,
            manifest=manifest,
        )

    # Truncation needed — allocate budget proportionally with priority weighting
    truncation_notes_parts: list[str] = []
    signal_contents: dict[SignalType, str] = {}

    # Allocate budget: higher priority types get proportionally more
    # Strategy: fill from highest priority, truncate from lowest
    remaining_budget = token_budget
    type_tokens: dict[SignalType, int] = {
        st: estimate_tokens(c) for st, c in raw_contents.items()
    }

    # Process in priority order (highest first)
    # Give each type up to its full size, but cap the lowest-priority types
    # when budget runs out
    for signal_type in SIGNAL_PRIORITY:
        if signal_type not in raw_contents:
            continue

        content = raw_contents[signal_type]
        content_tokens = type_tokens[signal_type]

        if content_tokens <= remaining_budget:
            # Fits entirely
            signal_contents[signal_type] = content
            remaining_budget -= content_tokens
        elif remaining_budget > 0:
            # Partial fit — truncate to remaining budget
            truncated = _truncate_content(content, remaining_budget)
            signal_contents[signal_type] = truncated
            original_tokens = content_tokens
            kept_tokens = estimate_tokens(truncated)
            pct = round((1 - kept_tokens / original_tokens) * 100)
            truncation_notes_parts.append(
                f"{signal_type.value}: truncated by ~{pct}% "
                f"({original_tokens} → {kept_tokens} tokens)"
            )
            remaining_budget = 0
        else:
            # No budget left — skip entirely
            truncation_notes_parts.append(
                f"{signal_type.value}: excluded entirely "
                f"({content_tokens} tokens)"
            )

    truncation_notes = "; ".join(truncation_notes_parts) if truncation_notes_parts else None
    manifest = _build_manifest(classified)

    return AnalysisContext(
        signal_contents=signal_contents,
        truncation_notes=truncation_notes,
        manifest=manifest,
    )


def _build_manifest(classified: dict[SignalType, list[BundleFile]]) -> BundleManifest:
    """Build a BundleManifest from classified signals."""
    all_files = []
    for file_list in classified.values():
        all_files.extend(file_list)
    total_size = sum(f.size_bytes for f in all_files)
    return BundleManifest(
        total_files=len(all_files),
        total_size_bytes=total_size,
        files=all_files,
    )
