# RAG-Enhanced Chunking & Quality Evals

> **Date**: 2026-03-19
> **Status**: Draft
> **Scope**: Improve bundle analysis quality and chat retrieval by replacing priority-weighted truncation with semantic retrieval (RAG) and adding LangGraph-based quality evaluation.

---

## Problem Statement

The current chunking strategy has four weaknesses:

1. **No sub-file chunking** — files are atomic units. A large log file either fits entirely or gets tail-truncated. Diagnostic signals in the middle are lost.
2. **Flat priority within signal types** — all pod logs are equal. A crashing pod's logs aren't ranked above a healthy pod's.
3. **Rough token estimation** — `len(text) // 4` can be 20-30% off for structured content (JSON, YAML), leading to over/under-filling the context window.
4. **Chat retrieval is blunt** — `get_file_contents` returns full files with no pagination. Large files can blow up a single chat turn's context, and the LLM must guess which file to look at.

Additionally, there is no quality gate on the LLM's analysis output. A report with generic remediations, missing signal types, or hallucinated file paths is returned as-is.

## Constraints

All changes must comply with the existing golden requirements:

- **GR-6**: No bundle content persisted to disk or sent to external services (other than the configured LLM). The embedding model runs locally. ChromaDB runs in ephemeral mode (in-memory only). Vector store collections are destroyed with the session.
- **GR-7**: Single `docker compose up`. No new containers. No new ports. No new required environment variables.
- **GR-5**: Analysis must demonstrate breadth across multiple signal types. RAG retrieval must ensure signal type diversity, not just top-K relevance.
- **GR-12**: Must work with arbitrary bundles. Chunking strategies must handle unknown file structures gracefully.

## Approach: RAG-Enhanced Context Assembly

Chosen over two alternatives:

- **Smart Chunking + Eval Only (no vector store)**: Too incremental — heuristic ranking doesn't solve the "signal buried in the middle of a file" problem.
- **Full RAG + Multi-Step Agent (LangGraph agent loop for analysis)**: Over-engineered for a hiring demo — multiple LLM calls per analysis increases latency and failure modes.

The selected approach uses semantic retrieval to improve *what content* the LLM sees, with a post-analysis eval chain as a quality safety net.

---

## Design

### 1. Content-Type-Aware Chunking

**New module**: `src/backend/app/bundle/chunker.py`

Runs after classification (existing `classifier.py` is untouched). Each chunk carries metadata: `file_path`, `signal_type`, `chunk_index`.

| Signal Type | Format | Strategy | Boundary |
|---|---|---|---|
| events | JSON | One chunk per event object | JSON array element |
| pod_logs | Plain text | Group by timestamp window (~30 lines) | Blank line or timestamp regex |
| cluster_info | Mixed | Fixed-size with overlap | 512 tokens, 50 token overlap |
| resource_definitions | YAML | One chunk per resource document | `---` YAML document separator |
| node_status | Mixed | Fixed-size with overlap | 512 tokens, 50 token overlap |
| other | Unknown | Fixed-size with overlap | 512 tokens, 50 token overlap |

**Rationale for hybrid approach**: Kubernetes bundle structured formats (JSON events, YAML resources) have natural boundaries that are cheap to detect. Splitting them mid-object would hurt retrieval quality. Fixed-size fallback keeps it simple for unknown formats. This satisfies GR-12 (arbitrary bundles).

### 2. Embedding & Vector Store

**New modules**: `src/backend/app/rag/embedder.py`, `src/backend/app/rag/store.py`

**Embedding model**: `all-MiniLM-L6-v2` via `sentence-transformers`
- Runs locally in-process — no external API calls (GR-6 compliant)
- 384-dimension embeddings, ~80MB model size
- ~1000 chunks/second on CPU

**Vector store**: ChromaDB in ephemeral mode (`chromadb.Client()`)
- One collection per session, named by `session_id`
- Collection deleted on session cleanup — lifecycle matches existing session TTL
- No disk writes, no external service (GR-6, GR-7 compliant)

**Upload pipeline change**:

```
Current:  parse → classify → create session → return JSON
Proposed: parse → classify → chunk → embed → store in ChromaDB → create session → return JSON
```

The upload endpoint remains a synchronous `POST` returning JSON. Chunking + embedding adds ~2-3s to the upload response time. This is acceptable because:
1. The frontend already shows a loading spinner during upload.
2. The alternative (async indexing) would complicate the flow — the analyze endpoint would need to wait for indexing to finish, adding state management complexity for no UX benefit.

If upload latency becomes a problem with very large bundles, indexing can be deferred to the start of the `/analyze` call (which is already an SSE stream and can emit progress events). This is an implementation-time optimization, not a design change.

The `Session` model gains a reference to the ChromaDB collection (in-memory object, not serialized). The existing `extracted_files` dict stays for the `get_file_contents` fallback tool.

**Embedding model is downloaded at Docker build time** (in Dockerfile), not at runtime, so first `docker compose up` doesn't stall.

**Fallback on embedding failure**: If the embedding model fails to load at runtime (corrupted file, OOM on constrained hardware), the system falls back to the existing priority-weighted truncation for analysis and disables the `search_bundle` tool for chat. The `get_file_contents` tool remains available. A warning is logged at startup and surfaced to the frontend on first analysis.

### 3. RAG-Enhanced Analysis

**Modified module**: `src/backend/app/analysis/context.py`

Replaces priority-weighted truncation with semantic retrieval.

**Diagnostic query set** (hardcoded, tuned for Kubernetes bundles):

```python
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
```

**Retrieval logic** (`src/backend/app/rag/retriever.py`):

1. Run each diagnostic query against the collection → top 10 results per query.
2. Deduplicate by chunk ID.
3. Score-weight: chunks appearing across multiple queries rank higher (multi-signal relevance).
4. Fill the token budget (100K) with highest-scored chunks, preserving signal type diversity — at least some representation from each signal type present in the bundle (GR-5 breadth compliance).
5. Group retrieved chunks by signal type for the prompt (same structure the LLM currently expects).

**What stays the same**: `AnalysisContext` model, prompt format, LLM provider interface, streaming response. The LLM still produces a `DiagnosticReport` JSON.

**Truncation notes evolve**: Instead of "pod_logs: excluded entirely," they now read "retrieved 87 of 342 chunks via semantic search; signal coverage: events(23), pod_logs(31), cluster_info(15), resource_definitions(12), node_status(6)."

### 4. RAG-Enhanced Chat Retrieval

**Modified module**: `src/backend/app/api/routes.py` (chat endpoint)

New `search_bundle` tool added alongside existing `get_file_contents`:

```python
SEARCH_BUNDLE_TOOL = {
    "name": "search_bundle",
    "description": "Semantically search the support bundle for content related to a query. "
                   "Returns the most relevant chunks with file paths and context. "
                   "Use this first to find relevant content, then use get_file_contents "
                   "only if you need the complete file.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what you're looking for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of chunks to return (default 10).",
            },
        },
        "required": ["query"],
    },
}
```

**Tool handler**: Queries the session's ChromaDB collection, returns top-K chunks formatted as:

```
--- [file_path] (signal_type, relevance: 0.87) ---
<chunk content>
```

**`get_file_contents` stays** as a fallback for when the LLM needs the complete file. Its description is updated to nudge the LLM toward `search_bundle` first.

**Chat context injection improves**: The current manifest listing (capped at 100 files) is replaced with a compact summary: signal type counts + top-5 most relevant file paths from the analysis report's source citations.

### 5. Quality Evals

**New module**: `src/backend/app/evals/evaluator.py`

**Phase 1 eval dimensions** (each scored 0-1, all programmatic — zero LLM cost):

| Dimension | Method | Cost |
|---|---|---|
| Coverage | Programmatic: compare `signal_types_analyzed` against bundle contents | Free |
| Citation accuracy | Programmatic: check each `SourceCitation.file_path` against `extracted_files` keys | Free |

**Phase 2 (deferred)**: LLM judge evals for actionability and coherence using LangGraph. Deferred until the RAG pipeline is proven — the programmatic checks provide the highest-value quality gates at zero cost. Adding LLM judges later is additive (no architectural changes needed).

**Flow**:

```
Analysis complete → DiagnosticReport
        ↓
  Programmatic checks first (free)
  Coverage score + Citation score
        ↓
  If programmatic checks pass:
    LLM judge checks (actionability + coherence)
        ↓
  Composite score ≥ 0.7?
    YES → return report
    NO  → re-run analysis with feedback (max 1 retry)
        → return best-scoring report
```

**Retry feedback structure**: When a retry is triggered, the re-analysis prompt includes:
- The composite score and per-dimension scores from the eval.
- Specific issues identified (e.g., "signal types cluster_info and node_status were not analyzed", "remediation for finding #2 is too generic — says 'check logs' without specifying which logs").
- The original report is NOT included — the LLM re-analyzes from the same retrieved context with the feedback as additional instruction.

**Key constraints**:
- Max 1 retry — caps latency and LLM cost at 2x worst case.
- Programmatic checks run first — avoids wasting LLM calls on obviously incomplete reports.
- Eval progress streamed to frontend: `{"type": "progress", "stage": "evaluating", "scores": {...}}`
- Eval scores attached to the report in a new optional field.

**LangGraph usage**: Simple linear graph with 4 eval nodes (2 programmatic, 2 LLM), a scoring node, and one conditional edge for retry. State management and conditional routing — not agentic behavior.

### 6. Dependency & Infrastructure Changes

**New Python dependencies**:

| Package | Purpose | Size Impact |
|---|---|---|
| `chromadb` | In-memory vector store | ~50MB |
| `sentence-transformers` | Embedding model runtime | ~30MB (package only) |
| `torch` (CPU-only) | Required by sentence-transformers | ~400MB |

**Deferred**: `langgraph` and `langchain-core` are not needed for Phase 1 (programmatic evals only). They will be added when LLM judge evals are implemented in Phase 2.

**Docker image impact**: Backend image grows from ~200MB to ~700-800MB, primarily due to PyTorch (CPU-only wheel). Embedding model downloaded at build time. First `docker compose build` takes longer but only happens once — subsequent rebuilds use cached layers.

**Alternative considered**: `onnxruntime` + ONNX-exported MiniLM (~50MB runtime vs ~400MB for PyTorch). If image size becomes a problem during implementation, this is a drop-in replacement that preserves the same embedding quality with ~8x smaller runtime. Deferred for now — PyTorch is simpler to set up and debug.

**Memory impact**: ChromaDB + embeddings for a typical bundle (~1000-3000 chunks) adds ~50-100MB per session. The existing `MAX_SESSIONS=20` cap and 4GB container memory limit are sufficient.

**No new containers. No new ports. No new required environment variables.**

Optional tuning variables (with defaults):
- `RAG_CHUNK_SIZE=512` — default token size for fixed-size chunks
- `RAG_CHUNK_OVERLAP=50` — overlap tokens for fixed-size chunks
- `EVAL_THRESHOLD=0.7` — minimum composite score to accept a report

Per GR-8, these must be documented in `.env.example` (with defaults) and in the README setup instructions, even though they are optional.

**Minimal frontend changes required**:
- The SSE hook (`useSSE.ts`) currently handles `chunk`, `error`, `warning`, and `done` event types. A new `progress` case is needed to surface `stage` and `scores` data to the UI during upload/analysis loading phases. This is a small addition to the existing switch statement.
- The `ReportPhase.tsx` progress stepper can be extended to display RAG indexing and eval stages. No structural changes — just new stage labels.
- Eval scores can optionally be shown as a confidence indicator on the report. Additive UI only.

**What doesn't change**:
- Session lifecycle — same TTL, eviction policy; collection cleanup hooks into existing `session_store.delete()`
- LLM provider interface — `analyze()` and `chat()` signatures unchanged
- API contract — same endpoints, same response shapes, new optional fields are additive only

---

## Architecture Decision Records

### ADR-004: Embedded RAG over External Vector Database

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: Improving analysis quality requires semantic search over bundle content. Options: (a) external vector DB container (Qdrant, Weaviate), (b) embedded in-process vector store (ChromaDB ephemeral), (c) no vector store (heuristic improvements only).
- **Decision**: ChromaDB embedded in ephemeral mode. One collection per session, destroyed on cleanup.
- **Rationale**: This is a hiring demo — every additional container is a failure mode during evaluation. Embedded approach gives full semantic search capability with zero infrastructure overhead. Data lifecycle matches the existing session model (in-memory, session-scoped). GR-6 and GR-7 compliance with no exceptions.
- **Golden Requirements Impact**: GR-6 (no persistence — ephemeral mode, no disk writes), GR-7 (no new containers — same `docker compose up`). No conflicts.
- **Consequences**:
  - Positive: Zero infrastructure overhead, same startup experience, full semantic search.
  - Negative: Not horizontally scalable. Acceptable — this is a single-user prototype.

### ADR-005: Local Embedding Model over API-Based Embeddings

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: Semantic search requires vector embeddings. Options: (a) API-based embeddings (OpenAI, Cohere), (b) local model via sentence-transformers.
- **Decision**: Local `all-MiniLM-L6-v2` via sentence-transformers, downloaded at Docker build time.
- **Rationale**: GR-6 prohibits sending bundle content to external services other than the configured LLM provider. API-based embeddings would send every chunk to a third-party service. Local model keeps all content in-process. The ~2s embedding time for a typical bundle is an acceptable trade-off.
- **Alternatives considered**: `onnxruntime` + ONNX-exported MiniLM would reduce the runtime from ~400MB (PyTorch CPU) to ~50MB. Deferred — PyTorch is simpler to set up and sentence-transformers has better documentation. If image size is a problem, ONNX is a drop-in replacement.
- **Golden Requirements Impact**: GR-6 (no bundle content to external services — directly enforced by running locally). No conflicts.
- **Consequences**:
  - Positive: Full GR-6 compliance, no API cost for embeddings, no network dependency.
  - Negative: Docker image grows ~500MB (PyTorch CPU-only wheel is the main contributor). Embedding quality slightly lower than API models. Both acceptable for a prototype.

### ADR-006: Content-Type-Aware Hybrid Chunking

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: Support bundles contain heterogeneous file types (JSON, YAML, plain text logs, unknown formats). Need a chunking strategy that preserves semantic boundaries where possible and degrades gracefully for unknown formats.
- **Decision**: Hybrid approach — structure-aware splitting for JSON (array elements), YAML (`---` document boundaries), and logs (timestamp-grouped lines); fixed-size with overlap (512 tokens, 50 overlap) for everything else.
- **Rationale**: Kubernetes bundles have natural boundaries that are cheap to detect. Splitting mid-YAML-resource or mid-JSON-event degrades retrieval quality. Fixed-size fallback handles GR-12 (arbitrary bundles) — unknown formats still get indexed, just without semantic boundaries.
- **Golden Requirements Impact**: GR-12 (arbitrary bundles — fallback strategy handles unknown formats), GR-5 (breadth — all signal types are chunked and indexed). No conflicts.
- **Consequences**:
  - Positive: Better retrieval quality for structured K8s content. Graceful degradation for unknown formats.
  - Negative: More complex chunking code with format-specific paths. Acceptable — the formats are well-defined and testable.

### ADR-007: LangGraph Post-Analysis Quality Evals

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: LLM analysis can produce reports with generic remediations, missing signal type coverage, or hallucinated file references. No quality gate currently exists.
- **Decision**: LangGraph eval chain with 4 dimensions (coverage, citation accuracy, actionability, coherence). Programmatic checks run first (free), LLM judges run only if programmatic checks pass. Max 1 retry with feedback.
- **Rationale**: Programmatic-first approach minimizes LLM cost. Single retry caps worst-case latency at 2x. LangGraph provides clean state management for the eval → retry conditional flow. The eval scores double as a confidence signal for the frontend.
- **Golden Requirements Impact**: GR-3 (actionable output — eval chain verifies actionability). GR-5 (breadth — coverage check verifies signal type representation). No conflicts.
- **Consequences**:
  - Positive: Catches low-quality reports before the user sees them. Provides confidence scoring.
  - Negative: Adds 2 LLM calls for LLM judge evals + potential retry. Worst case ~2x analysis time. Acceptable — eval progress is streamed to the user during loading.

---

## Testing Strategy

- **Chunker unit tests**: Verify each format strategy (JSON splitting, YAML boundary detection, log grouping, fixed-size fallback) with fixture files.
- **Embedding integration test**: Verify chunks are embedded and retrievable from ChromaDB with expected similarity scores.
- **Retrieval test**: Verify diagnostic queries return relevant chunks and signal type diversity is maintained.
- **Eval unit tests**: Verify programmatic checks (coverage, citation accuracy) with mock reports. Verify LLM judge scoring with canned responses.
- **End-to-end test**: Upload a test bundle → verify retrieved chunks are more relevant than the old truncation approach (compare analysis reports).
