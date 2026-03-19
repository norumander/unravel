# DECISIONS.md

## ADR Index

| # | Title | Status | Date |
|---|---|---|---|
| ADR-001 | Tech stack selection | Accepted | 2026-03-15 |
| ADR-002 | In-memory only session storage | Accepted | 2026-03-15 |
| ADR-003 | Stdout-only observability (no Langfuse) | Accepted | 2026-03-15 |
| ADR-004 | Embedded RAG over external vector database | Accepted | 2026-03-19 |
| ADR-005 | Local embedding model over API-based embeddings | Accepted | 2026-03-19 |
| ADR-006 | Content-type-aware hybrid chunking | Accepted | 2026-03-19 |
| ADR-007 | LangGraph post-analysis quality evals | Accepted | 2026-03-19 |

---

## ADR-001: Tech Stack Selection

- **Status**: Accepted
- **Date**: 2026-03-15
- **Context**: Need to select language, framework, and tooling for a prototype web app that ingests Kubernetes support bundles and uses LLM for analysis. The hiring brief imposes no technology constraints. Must support streaming SSE, LLM SDK integration (Anthropic + OpenAI), tar.gz extraction, and Docker Compose deployment.
- **Decision**: Python 3.12 + FastAPI (backend), TypeScript + React 18 + Vite (frontend), Tailwind CSS (styling), pytest (backend tests), Vitest (frontend tests), Docker Compose (runtime). Rationale:
  - Python has the strongest LLM SDK ecosystem (official Anthropic + OpenAI packages with streaming + tool-use support).
  - FastAPI is async-native with built-in SSE via StreamingResponse — minimal boilerplate.
  - React + Vite is a standard, fast SPA stack. TypeScript aligns with Replicated's frontend (evaluator familiarity).
  - Tailwind enables rapid UI development without CSS architecture overhead.
  - Docker Compose satisfies GR-7 (single-command startup).
- **Golden Requirements Impact**: GR-4 (web app — satisfied by React SPA + FastAPI), GR-7 (single command — Docker Compose). No conflicts.
- **Consequences**:
  - Positive: Fast development, excellent LLM SDK support, familiar stack for evaluator.
  - Negative: Two languages (Python + TypeScript) increases container count. Acceptable for a prototype.

---

## ADR-002: In-Memory Only Session Storage

- **Status**: Accepted
- **Date**: 2026-03-15
- **Context**: GR-6 requires bundle data to be treated as sensitive with no disk persistence. The PRD explicitly excludes persistent storage. Need to store session state (bundle data, manifest, report, chat history) during active analysis.
- **Decision**: Use a Python dict mapping session_id → Session objects. No database, no file-based cache, no Redis. Data lives only in the FastAPI process memory and is cleared on session delete or server restart.
- **Golden Requirements Impact**: GR-6 (data sensitivity — directly enforced: no disk writes, no external storage). No conflicts.
- **Consequences**:
  - Positive: Simplest possible implementation. Zero infrastructure dependencies. Guaranteed data cleanup on restart. Full GR-6 compliance.
  - Negative: Data lost on server restart. No horizontal scaling. Acceptable for a single-user prototype.

---

## ADR-003: Stdout-Only Observability (No Langfuse/LangSmith)

- **Status**: Accepted
- **Date**: 2026-03-15
- **Context**: PRD requires structured logging for LLM calls. External observability platforms (Langfuse, LangSmith, Datadog) are explicitly out of scope per PRD. GR-6 prohibits sending bundle content to external services.
- **Decision**: Structured JSON logging to stdout only. Each LLM call emits one log line with: timestamp, session_id, call_type, provider, model, input_tokens, output_tokens, latency_ms, status. Visible via `docker compose logs`. No bundle content in logs.
- **Golden Requirements Impact**: GR-6 (no bundle content to external services — no external observability services used; no bundle content in log entries). No conflicts.
- **Consequences**:
  - Positive: Zero additional dependencies. GR-6 compliant. Logs visible in Docker Compose output.
  - Negative: No prompt/response tracing, no dashboards. In production, a self-hosted Langfuse deployment would add full tracing while maintaining data sovereignty.
  - Neutral: Sufficient for prototype evaluation. Evaluator can see LLM call metadata in `docker compose logs`.

---

## ADR-004: Embedded RAG over External Vector Database

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: Improving analysis quality requires semantic search over bundle content. Options: (a) external vector DB container (Qdrant, Weaviate), (b) embedded in-process vector store (ChromaDB ephemeral), (c) no vector store (heuristic improvements only).
- **Decision**: ChromaDB embedded in ephemeral mode. One collection per session, destroyed on cleanup.
- **Rationale**: This is a hiring demo — every additional container is a failure mode during evaluation. Embedded approach gives full semantic search capability with zero infrastructure overhead. Data lifecycle matches the existing session model (in-memory, session-scoped). GR-6 and GR-7 compliance with no exceptions.
- **Golden Requirements Impact**: GR-6 (no persistence — ephemeral mode, no disk writes), GR-7 (no new containers — same `docker compose up`). No conflicts.
- **Consequences**:
  - Positive: Zero infrastructure overhead, same startup experience, full semantic search.
  - Negative: Not horizontally scalable. Acceptable — this is a single-user prototype.

---

## ADR-005: Local Embedding Model over API-Based Embeddings

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: Semantic search requires vector embeddings. Options: (a) API-based embeddings (OpenAI, Cohere), (b) local model via sentence-transformers.
- **Decision**: Local `all-MiniLM-L6-v2` via sentence-transformers, downloaded at Docker build time.
- **Rationale**: GR-6 prohibits sending bundle content to external services other than the configured LLM provider. API-based embeddings would send every chunk to a third-party service. Local model keeps all content in-process. The ~2s embedding time for a typical bundle is an acceptable trade-off.
- **Alternatives considered**: `onnxruntime` + ONNX-exported MiniLM (~50MB runtime vs ~400MB for PyTorch CPU). Deferred — PyTorch is simpler to set up and sentence-transformers has better documentation. If image size is a problem, ONNX is a drop-in replacement.
- **Golden Requirements Impact**: GR-6 (no bundle content to external services — directly enforced by running locally). No conflicts.
- **Consequences**:
  - Positive: Full GR-6 compliance, no API cost for embeddings, no network dependency.
  - Negative: Docker image grows ~500MB (PyTorch CPU-only wheel is the main contributor). Embedding quality slightly lower than API models. Both acceptable for a prototype.

---

## ADR-006: Content-Type-Aware Hybrid Chunking

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: Support bundles contain heterogeneous file types (JSON, YAML, plain text logs, unknown formats). Need a chunking strategy that preserves semantic boundaries where possible and degrades gracefully for unknown formats.
- **Decision**: Hybrid approach — structure-aware splitting for JSON (array elements), YAML (`---` document boundaries), and logs (timestamp-grouped lines); fixed-size with overlap (512 tokens, 50 overlap) for everything else.
- **Rationale**: Kubernetes bundles have natural boundaries that are cheap to detect. Splitting mid-YAML-resource or mid-JSON-event degrades retrieval quality. Fixed-size fallback handles GR-12 (arbitrary bundles) — unknown formats still get indexed, just without semantic boundaries.
- **Golden Requirements Impact**: GR-12 (arbitrary bundles — fallback strategy handles unknown formats), GR-5 (breadth — all signal types are chunked and indexed). No conflicts.
- **Consequences**:
  - Positive: Better retrieval quality for structured K8s content. Graceful degradation for unknown formats.
  - Negative: More complex chunking code with format-specific paths. Acceptable — the formats are well-defined and testable.

---

## ADR-007: LangGraph Post-Analysis Quality Evals

- **Status**: Accepted
- **Date**: 2026-03-19
- **Context**: LLM analysis can produce reports with generic remediations, missing signal type coverage, or hallucinated file references. No quality gate currently exists.
- **Decision**: LangGraph eval chain with 4 dimensions (coverage, citation accuracy, actionability, coherence). Programmatic checks run first (free), LLM judges run only if programmatic checks pass. Max 1 retry with feedback.
- **Rationale**: Programmatic-first approach minimizes LLM cost. Single retry caps worst-case latency at 2x. LangGraph provides clean state management for the eval → retry conditional flow. The eval scores double as a confidence signal for the frontend.
- **Golden Requirements Impact**: GR-3 (actionable output — eval chain verifies actionability). GR-5 (breadth — coverage check verifies signal type representation). No conflicts.
- **Consequences**:
  - Positive: Catches low-quality reports before the user sees them. Provides confidence scoring.
  - Negative: Adds 2 LLM calls for LLM judge evals + potential retry. Worst case ~2x analysis time. Acceptable — eval progress is streamed to the user during loading.
