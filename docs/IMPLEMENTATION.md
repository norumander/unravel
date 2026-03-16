# IMPLEMENTATION.md

## Current Focus

Phase 1 complete. Ready to scaffold (Phase 2) then begin implementation.

## Tasks

### TASK-001: Data Models
- **Status**: TODO
- **Priority**: P0
- **Description**: Define all Pydantic models and enums: Session, BundleManifest, BundleFile, SignalType, DiagnosticReport, Finding, Severity, ChatMessage, ToolCall, AnalysisContext.
- **Acceptance Criteria**:
  - [ ] All models defined in `src/backend/models/` with proper types
  - [ ] SignalType and Severity enums serialize to lowercase strings
  - [ ] Models can be instantiated and serialized to JSON
  - [ ] Unit tests verify serialization round-trip for each model
- **Notes**: Foundation for everything else. No dependencies.

### TASK-002: Bundle Parser
- **Status**: TODO
- **Priority**: P0
- **Description**: Implement tar.gz upload validation and in-memory extraction. Validate file is tar.gz (magic bytes check), enforce 500MB size limit, extract all files to a dict[str, bytes] with path traversal prevention. Return BundleManifest.
- **Acceptance Criteria**:
  - [ ] Valid .tar.gz → returns BundleManifest with correct file count and sizes
  - [ ] Non-tar.gz file → raises InvalidBundleError
  - [ ] File >500MB → raises BundleTooLargeError
  - [ ] Path traversal attempt (e.g., `../../etc/passwd`) → file is skipped or path is sanitized
  - [ ] No files written to disk (GR-6)
  - [ ] Unit tests for all cases including edge cases (empty archive, nested dirs)
- **Dependencies**: TASK-001

### TASK-003: Signal Classifier
- **Status**: TODO
- **Priority**: P0
- **Description**: Classify bundle files into signal types based on file path patterns. Use known Troubleshoot directory conventions. Unknown paths → "other".
- **Acceptance Criteria**:
  - [ ] Files in `*/logs/` or `*/podlogs/` paths → pod_logs
  - [ ] Files in `*/cluster-info/` paths → cluster_info
  - [ ] Files in `*/cluster-resources/` paths → resource_definitions
  - [ ] Files in `*/events.json` or `*/events/` paths → events
  - [ ] Files in `*/node_list*` or `*/nodes/` paths → node_status
  - [ ] Unrecognized paths → other
  - [ ] Classification is path-based only, not content-based (GR-12)
  - [ ] Unit tests with realistic Troubleshoot bundle paths
- **Dependencies**: TASK-001

### TASK-004: Session Store
- **Status**: TODO
- **Priority**: P0
- **Description**: In-memory session management. Create, get, delete sessions. Session holds bundle data, manifest, classified signals, report, chat history.
- **Acceptance Criteria**:
  - [ ] `create()` returns a new Session with unique ID
  - [ ] `get()` returns existing session or raises SessionNotFoundError
  - [ ] `delete()` removes session and all associated data
  - [ ] After delete, get() raises SessionNotFoundError
  - [ ] No disk I/O (GR-6)
  - [ ] Unit tests for CRUD operations
- **Dependencies**: TASK-001

### TASK-005: Context Assembler & Truncation
- **Status**: TODO
- **Priority**: P0
- **Description**: Assemble classified bundle content into AnalysisContext for LLM prompt. Implement priority-based truncation when content exceeds 100K token budget. Priority: events > pod_logs > cluster_info > resource_definitions > node_status. Within each type, preserve most recent content. Annotate what was truncated.
- **Acceptance Criteria**:
  - [ ] Small bundle (under budget) → all content included, no truncation notes
  - [ ] Large bundle (over budget) → content truncated to fit, lower-priority types truncated first
  - [ ] Truncation notes list which types were truncated and by how much
  - [ ] Events and pod_logs preserved preferentially
  - [ ] Token estimation is approximately correct (within 10% of budget)
  - [ ] Unit tests with synthetic data above and below token budget
- **Dependencies**: TASK-001, TASK-003

### TASK-006: LLM Provider Interface & Factory
- **Status**: TODO
- **Priority**: P0
- **Description**: Define abstract LLMProvider class with `analyze()` and `chat()` methods. Implement factory function that reads `LLM_PROVIDER` env var and returns the appropriate implementation. Define AnalysisContext and ToolDef types.
- **Acceptance Criteria**:
  - [ ] Abstract class with `analyze()` and `chat()` async generator methods
  - [ ] Factory returns AnthropicProvider when LLM_PROVIDER=anthropic
  - [ ] Factory returns OpenAIProvider when LLM_PROVIDER=openai
  - [ ] Factory raises error for unknown provider value
  - [ ] Factory raises error when required API key env var is missing
  - [ ] Unit tests for factory logic (no live LLM calls)
- **Dependencies**: TASK-001

### TASK-007: Anthropic Provider Implementation
- **Status**: TODO
- **Priority**: P0
- **Description**: Implement AnthropicProvider using the Anthropic Python SDK. Support streaming analysis (returns structured report) and streaming chat with tool-use (get_file_contents). Handle API errors gracefully.
- **Acceptance Criteria**:
  - [ ] `analyze()` streams tokens via AsyncIterator, final output is parseable DiagnosticReport JSON
  - [ ] `chat()` streams tokens, supports tool_use blocks for get_file_contents
  - [ ] API errors (auth, rate limit, network) → raises LLMError with human-readable message
  - [ ] Reports input_tokens, output_tokens, model name for logging
  - [ ] Unit tests with mocked Anthropic SDK responses (streaming + tool-use)
- **Dependencies**: TASK-006

### TASK-008: OpenAI Provider Implementation
- **Status**: TODO
- **Priority**: P1
- **Description**: Implement OpenAIProvider using the OpenAI Python SDK. Same interface as Anthropic: streaming analysis and streaming chat with tool-use.
- **Acceptance Criteria**:
  - [ ] `analyze()` streams tokens via AsyncIterator, final output is parseable DiagnosticReport JSON
  - [ ] `chat()` streams tokens, supports function_call for get_file_contents
  - [ ] API errors → raises LLMError with human-readable message
  - [ ] Reports input_tokens, output_tokens, model name for logging
  - [ ] Unit tests with mocked OpenAI SDK responses (streaming + tool-use)
- **Dependencies**: TASK-006

### TASK-009: Structured LLM Logger
- **Status**: TODO
- **Priority**: P1
- **Description**: Implement structured JSON logging for every LLM API call. Fields: timestamp, session_id, call_type, provider, model, input_tokens, output_tokens, latency_ms, status. Output to stdout. No bundle content in logs (GR-6).
- **Acceptance Criteria**:
  - [ ] Every LLM call emits exactly one JSON log line to stdout
  - [ ] All required fields present and correctly typed
  - [ ] No bundle file content appears in log output
  - [ ] Unit tests verify log format and content
- **Dependencies**: TASK-006

### TASK-010: Upload API Endpoint
- **Status**: TODO
- **Priority**: P0
- **Description**: Implement `POST /api/upload` endpoint. Accept multipart file upload, validate with bundle parser, classify signals, create session, return session_id + manifest.
- **Acceptance Criteria**:
  - [ ] Valid .tar.gz → 200 with session_id and manifest JSON
  - [ ] Non-tar.gz → 400 with error message
  - [ ] >500MB → 413 with error message
  - [ ] Session created in session store with classified signals
  - [ ] Integration test with httpx TestClient
- **Dependencies**: TASK-002, TASK-003, TASK-004

### TASK-011: Analyze API Endpoint (SSE)
- **Status**: TODO
- **Priority**: P0
- **Description**: Implement `GET /api/analyze/{session_id}` endpoint. Assemble context, call LLM provider analyze(), stream response via SSE. Parse final report and store on session. Emit chunk events during streaming, report event on completion, error event on failure.
- **Acceptance Criteria**:
  - [ ] Response Content-Type is `text/event-stream`
  - [ ] Chunk events stream incrementally
  - [ ] Final report event contains valid DiagnosticReport JSON
  - [ ] Report stored on session after completion
  - [ ] Invalid session_id → 404
  - [ ] LLM error → error SSE event with human-readable message
  - [ ] Integration test with mocked LLM provider
- **Dependencies**: TASK-005, TASK-006, TASK-007, TASK-009, TASK-010

### TASK-012: Chat API Endpoint (SSE + Tool-Use)
- **Status**: TODO
- **Priority**: P0
- **Description**: Implement `POST /api/chat/{session_id}` endpoint. Accept user message, provide report + manifest as context, call LLM provider chat() with get_file_contents tool, stream response via SSE. Maintain chat history on session.
- **Acceptance Criteria**:
  - [ ] Response Content-Type is `text/event-stream`
  - [ ] Chunk events stream incrementally
  - [ ] Tool-use events emitted when LLM requests file contents
  - [ ] get_file_contents tool retrieves correct file from session
  - [ ] Chat history persists across multiple messages
  - [ ] Invalid session_id → 404
  - [ ] LLM error → error SSE event
  - [ ] Integration test with mocked LLM provider (including tool-use flow)
- **Dependencies**: TASK-004, TASK-006, TASK-007, TASK-009, TASK-011

### TASK-013: Session Delete Endpoint
- **Status**: TODO
- **Priority**: P1
- **Description**: Implement `DELETE /api/sessions/{session_id}`. Remove session from store. Return 200 on success, 404 if not found.
- **Acceptance Criteria**:
  - [ ] Existing session → 200 `{ "deleted": true }`
  - [ ] Non-existent session → 404
  - [ ] After delete, GET analyze and POST chat for that session return 404
  - [ ] Integration test
- **Dependencies**: TASK-004

### TASK-014: Frontend — Upload Phase
- **Status**: TODO
- **Priority**: P0
- **Description**: React component for bundle upload. Drag-and-drop zone + file picker. Shows upload progress, displays manifest on success, shows errors on failure. Transitions to report phase on successful upload.
- **Acceptance Criteria**:
  - [ ] Drag-and-drop file upload works
  - [ ] File picker fallback works
  - [ ] Upload progress indicator visible
  - [ ] Success → displays file count and transitions to analysis
  - [ ] Error (400, 413) → displays error message inline
  - [ ] Vitest + RTL tests for component rendering and state transitions
- **Dependencies**: TASK-010

### TASK-015: Frontend — Report Phase
- **Status**: TODO
- **Priority**: P0
- **Description**: React component for streaming report display. Connects to SSE analyze endpoint, renders content incrementally. On completion, displays structured report with findings (severity, title, description, root cause, remediation). Transitions to chat phase.
- **Acceptance Criteria**:
  - [ ] SSE connection established to analyze endpoint
  - [ ] Content renders incrementally as chunks arrive
  - [ ] Final report renders all findings with all fields
  - [ ] Findings sorted by severity (critical → warning → info)
  - [ ] Error events displayed inline
  - [ ] Vitest + RTL tests with mocked SSE
- **Dependencies**: TASK-011

### TASK-016: Frontend — Chat Phase
- **Status**: TODO
- **Priority**: P0
- **Description**: React chat interface. Message input, streaming response display, tool-use indicators (shows when LLM is retrieving a file). Chat history displayed as conversation thread.
- **Acceptance Criteria**:
  - [ ] User can type and send messages
  - [ ] Responses stream in via SSE
  - [ ] Tool-use events show file retrieval indicator
  - [ ] Chat history persists in UI across messages
  - [ ] Error events displayed inline
  - [ ] Vitest + RTL tests with mocked SSE
- **Dependencies**: TASK-012, TASK-015

### TASK-017: Docker Compose & Environment Config
- **Status**: TODO
- **Priority**: P0
- **Description**: Create docker-compose.yml (frontend + backend containers), Dockerfiles for each, .env.example with all required variables. Verify `docker compose up` starts both services and app is accessible at localhost:3000.
- **Acceptance Criteria**:
  - [ ] `docker compose up` starts frontend and backend
  - [ ] Frontend accessible at http://localhost:3000
  - [ ] Backend API accessible at http://localhost:8000
  - [ ] Frontend proxies /api/* to backend
  - [ ] `.env.example` contains LLM_PROVIDER, ANTHROPIC_API_KEY, OPENAI_API_KEY, and model config
  - [ ] Missing API key → backend starts but returns clear error on LLM calls
- **Dependencies**: TASK-010, TASK-011, TASK-012, TASK-013, TASK-014, TASK-015, TASK-016

### TASK-018: LLM Error Handling & Resilience
- **Status**: TODO
- **Priority**: P1
- **Description**: Ensure all LLM failure modes (invalid key, rate limit, network error, context length exceeded) produce structured error responses. Frontend displays errors inline. Session remains usable after error.
- **Acceptance Criteria**:
  - [ ] Invalid API key → error SSE event with auth-related message
  - [ ] Network timeout → error SSE event with timeout message
  - [ ] Context too long → error SSE event with context message
  - [ ] Session remains usable after any error (can retry)
  - [ ] Tests for each failure mode with mocked providers
- **Dependencies**: TASK-011, TASK-012

### TASK-019: README & Documentation
- **Status**: TODO
- **Priority**: P1
- **Description**: Write README.md with project description, architecture overview, prerequisites, setup instructions (env config, docker compose up), usage walkthrough. Write MY_APPROACH_AND_THOUGHTS.md (≤500 words).
- **Acceptance Criteria**:
  - [ ] README contains "docker compose", "env", "setup" (case-insensitive)
  - [ ] README includes architecture overview with diagram
  - [ ] MY_APPROACH_AND_THOUGHTS.md exists and word count ≤ 500
  - [ ] .env.example contains LLM_PROVIDER, ANTHROPIC_API_KEY, OPENAI_API_KEY
  - [ ] No TODO or FIXME comments in any source file
- **Dependencies**: TASK-017

## Completed

*(none yet)*

## Backlog

- Stretch: Severity-based report filtering (frontend)
- Stretch: Bundle comparison (two bundles, diff analysis)
- Stretch: Export report as Markdown
- Stretch: Confidence scoring on findings
- Stretch: Source citing for findings

## Session Log

### Checkpoint — 2026-03-15 23:05
- **Phase**: Phase 0 — Init & Plan (COMPLETE)
- **Completed**: Read PRD.md and GOLDEN.md, identified tech stack, created .gitignore, committed bootstrap inputs, presented planning gate, user confirmed.
- **State**: Project has CLAUDE.md, PRD.md, GOLDEN.md, .gitignore committed. No docs generated yet.
- **Next**: Execute Phase 1 — Generate module files.
- **Blockers**: None
- **Open Questions**: None

### Checkpoint — 2026-03-15 23:15
- **Phase**: Phase 1 — Generate Module Files (COMPLETE)
- **Completed**: Generated ARCHITECTURE.md, IMPLEMENTATION.md (19 tasks), DECISIONS.md (3 ADRs), TESTING.md.
- **State**: All module files generated. 19 tasks defined and dependency-ordered. Ready for Phase 2 (scaffold).
- **Next**: Execute Phase 2 — Scaffold project structure, install dependencies, configure tooling.
- **Blockers**: None
- **Open Questions**: None
