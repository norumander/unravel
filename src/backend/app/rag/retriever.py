"""Diagnostic query retriever — retrieves relevant chunks for analysis and chat."""

import logging

from app.analysis.context import CHARS_PER_TOKEN, estimate_tokens
from app.models.schemas import AnalysisContext, BundleFile, BundleManifest, SignalType
from app.rag.embedder import RAGStore, SearchResult

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_BUDGET = 100_000

DIAGNOSTIC_QUERIES = [
    "pod crash loop backoff restart failure",
    "OOM killed memory limit exceeded",
    "image pull error registry authentication",
    "node not ready disk pressure memory pressure",
    "pending pod scheduling failed insufficient resources",
    "certificate expired TLS handshake error",
    "connection refused timeout network policy",
    "volume mount failed persistent volume claim",
    "RBAC permission denied forbidden",
    "deployment rollout failed replica unavailable",
    "liveness readiness probe failed",
    "DNS resolution failure service discovery",
]

_MIN_SIGNAL_BUDGET_PCT = 0.05


def retrieve_analysis_context(
    store: RAGStore,
    collection_name: str,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    bundle_manifest: BundleManifest | None = None,
) -> AnalysisContext:
    """Retrieve and assemble an AnalysisContext from the RAG store using diagnostic queries.

    Runs a fixed set of diagnostic queries against the collection, deduplicates results,
    applies a multi-query relevance bonus, and enforces signal-type diversity before
    filling the remaining token budget.

    Args:
        store: Initialized RAGStore.
        collection_name: Name of the ChromaDB collection to query.
        token_budget: Maximum token budget for the assembled context.
        bundle_manifest: Optional BundleManifest to embed in the returned context.

    Returns:
        An AnalysisContext with signal_contents keyed by SignalType.
    """
    all_results: dict[str, SearchResult] = {}
    hit_counts: dict[str, int] = {}

    for query in DIAGNOSTIC_QUERIES:
        results = store.query(collection_name, query, n_results=10)
        for r in results:
            chunk_id = f"{r.file_path}::{r.chunk_index}"
            if chunk_id not in all_results or r.score > all_results[chunk_id].score:
                all_results[chunk_id] = r
            hit_counts[chunk_id] = hit_counts.get(chunk_id, 0) + 1

    scored: list[tuple[str, SearchResult, float]] = []
    for chunk_id, result in all_results.items():
        multi_query_bonus = min(hit_counts[chunk_id] * 0.1, 0.5)
        combined_score = result.score + multi_query_bonus
        scored.append((chunk_id, result, combined_score))

    scored.sort(key=lambda x: x[2], reverse=True)

    signal_types_present: set[SignalType] = {r.signal_type for _, r, _ in scored}
    min_per_type = max(1, int(token_budget * _MIN_SIGNAL_BUDGET_PCT / 200))

    selected: list[SearchResult] = []
    selected_ids: set[str] = set()
    remaining_budget = token_budget

    # First pass: guarantee minimum representation for each signal type
    for st in signal_types_present:
        type_results = [
            (cid, r, s) for cid, r, s in scored
            if r.signal_type == st and cid not in selected_ids
        ]
        for cid, r, _ in type_results[:min_per_type]:
            tokens = estimate_tokens(r.text)
            if tokens <= remaining_budget:
                selected.append(r)
                selected_ids.add(cid)
                remaining_budget -= tokens

    # Second pass: fill remaining budget greedily by score
    for chunk_id, result, _ in scored:
        if chunk_id in selected_ids:
            continue
        tokens = estimate_tokens(result.text)
        if tokens > remaining_budget:
            continue
        selected.append(result)
        selected_ids.add(chunk_id)
        remaining_budget -= tokens

    signal_contents: dict[SignalType, str] = {}
    for result in selected:
        header = f"--- {result.file_path} ---\n"
        content = header + result.text
        if result.signal_type in signal_contents:
            signal_contents[result.signal_type] += "\n\n" + content
        else:
            signal_contents[result.signal_type] = content

    type_counts: dict[str, int] = {}
    for r in selected:
        type_counts[r.signal_type.value] = type_counts.get(r.signal_type.value, 0) + 1
    total_available = len(all_results)
    total_selected = len(selected)
    coverage = ", ".join(f"{k}({v})" for k, v in sorted(type_counts.items()))
    truncation_notes = (
        f"retrieved {total_selected} of {total_available} unique chunks via semantic search; "
        f"signal coverage: {coverage}"
    )

    manifest = bundle_manifest or BundleManifest(total_files=0, total_size_bytes=0, files=[])

    return AnalysisContext(
        signal_contents=signal_contents,
        truncation_notes=truncation_notes,
        manifest=manifest,
    )


def retrieve_for_query(
    store: RAGStore,
    collection_name: str,
    query: str,
    max_results: int = 10,
) -> list[SearchResult]:
    """Retrieve the most relevant chunks for an ad-hoc query (e.g. chat search tool).

    Args:
        store: Initialized RAGStore.
        collection_name: Name of the ChromaDB collection to query.
        query: Natural language query string.
        max_results: Maximum number of results to return.

    Returns:
        List of SearchResult ordered by descending relevance score.
    """
    return store.query(collection_name, query, n_results=max_results)
