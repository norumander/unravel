# DECISIONS.md

## ADR Index

| # | Title | Status | Date |
|---|---|---|---|
| ADR-001 | Tech stack selection | Accepted | 2026-03-15 |
| ADR-002 | In-memory only session storage | Accepted | 2026-03-15 |
| ADR-003 | Stdout-only observability (no Langfuse) | Accepted | 2026-03-15 |

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
