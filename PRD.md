# PRD.md

> **Development Methodology**: This project is built using agentic development (Claude Code).
> All requirements must be unambiguous and testable by automated tests.
> The agent follows strict TDD, makes atomic commits, and uses the CLAUDE.md bootstrap protocol.
> If a requirement can't be verified with a test, the agent can't know when to stop.

## Project Name

unravel

## One-Liner

A web app that ingests Kubernetes Troubleshoot support bundles, uses AI to produce a structured diagnostic report, and supports interactive follow-up investigation via chat.

## Problem Statement

Replicated's Troubleshoot tool generates support bundles — tar.gz archives of Kubernetes cluster state, logs, events, and metrics — for remote debugging. ISV developers receive these bundles when their customers' deployments break, but they have no access to the live system.

Today, analyzing a bundle is manual: engineers sift through large archives, correlate signals across log sources, and rely on tribal knowledge of common failure patterns. Simple misconfigurations consume disproportionate time. Complex issues consume hours of multi-engineer investigation.

Replicated is actively building AI tooling to automate this analysis. This prototype demonstrates a viable approach: automated triage (structured report identifying issues, root causes, and remediations) followed by interactive investigation (chat grounded in the bundle data with on-demand file retrieval).

This is a take-home hiring project for Replicated. The evaluator will run it against real support bundles, review the repo, and watch a 2-minute demo video.

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Language (backend) | Python 3.12 | Best LLM ecosystem; Anthropic + OpenAI SDKs, streaming, tar extraction |
| Framework (backend) | FastAPI | Async-native, SSE support, lightweight |
| Language (frontend) | TypeScript | Aligns with Replicated's frontend stack |
| Framework (frontend) | React 18 + Vite | SPA for upload → report → chat flow |
| Database | None | All state is in-memory per session. No persistence (GR-6). |
| Test Framework (backend) | pytest + pytest-asyncio | Standard for async FastAPI testing |
| Test Framework (frontend) | Vitest + React Testing Library | Vite-native, fast |
| Build/Runtime | Docker Compose | Single `docker compose up` (GR-7) |
| LLM | Anthropic Claude + OpenAI GPT | Swappable behind provider interface; configurable via env var |
| Styling | Tailwind CSS | Utility-first, fast to build, clean output |

## Requirements

### Core (MVP — must ship)

1. **Bundle upload and extraction.** The system must accept a `.tar.gz` file upload via the web UI, extract its contents in memory, and return a bundle manifest (list of files with paths and sizes). Uploads of non-tar.gz files must be rejected with a clear error message. Maximum upload size: 500MB.
   - *Test: Upload a valid .tar.gz → receive 200 with manifest JSON containing file paths. Upload a .txt file → receive 400 with error message. Upload a file >500MB → receive 413.*

2. **Signal type classification.** The system must classify extracted bundle files into five signal types: pod logs, cluster-info, resource definitions, events, and node status. Files that do not match any known type must be classified as "other" and excluded from primary analysis. Classification must be based on file path patterns within the bundle directory structure, not file content.
   - *Test: Given a bundle containing files in standard Troubleshoot paths, each file is classified into the correct signal type. Unknown paths are classified as "other."*

3. **Multi-signal LLM analysis with structured report.** The system must send classified bundle content to the configured LLM provider and produce a structured diagnostic report containing: (a) an executive summary (1–3 sentences), (b) a list of findings, each with a severity level (critical / warning / info), a title, a description, a root cause hypothesis, and a suggested remediation. The report must include findings derived from at least 3 of the 5 signal types when they are present in the bundle.
   - *Test: Given a bundle with files across all 5 signal types, the returned report contains an executive summary, at least one finding, and findings reference at least 3 signal types. Each finding has all required fields (severity, title, description, root_cause, remediation).*

4. **Streaming responses.** Both the initial analysis report and chat responses must be delivered via Server-Sent Events (SSE). The frontend must render content incrementally as tokens arrive.
   - *Test: Initiate an analysis request → response Content-Type is `text/event-stream`. Events arrive incrementally (multiple `data:` lines before the stream closes). Frontend renders partial content before stream completes.*

5. **Interactive chat with tool-use file retrieval.** After the report is generated, the user must be able to ask follow-up questions in a chat interface. The LLM receives the diagnostic report and bundle manifest as context. When the LLM needs to inspect a specific file from the bundle, it uses a `get_file_contents` tool call (function calling) to retrieve the file's content, which is injected into the conversation. Chat history is maintained for the duration of the session.
   - *Test: Send a chat message referencing a specific file in the bundle → the LLM issues a tool call for that file → the tool result is included in the response context → the response references content from that file. Chat history persists across multiple messages within a session.*

6. **Swappable LLM provider.** The system must support both Anthropic Claude and OpenAI GPT models behind a common provider interface. The active provider is selected via an environment variable (`LLM_PROVIDER=anthropic` or `LLM_PROVIDER=openai`). Both providers must support streaming responses and tool-use for chat file retrieval.
   - *Test: Set `LLM_PROVIDER=anthropic` → analysis and chat use the Anthropic SDK. Set `LLM_PROVIDER=openai` → analysis and chat use the OpenAI SDK. Both produce a valid structured report and support tool-use in chat.*

7. **Smart context truncation.** When the total extracted bundle content exceeds 100,000 tokens, the system must truncate content to fit within the LLM context window. Truncation strategy: prioritize content by signal type relevance (events and pod logs first, then cluster-info, then resource definitions, then node status), truncate within each type by recency (most recent log entries preserved), and include a note in the LLM prompt indicating which content was truncated.
   - *Test: Given a bundle whose extracted content exceeds 100,000 tokens, the context sent to the LLM is within the token budget. Events and pod logs are present. Truncated types are noted in the prompt.*

8. **Session-scoped data handling.** All bundle data must be held in memory only. No bundle content may be written to disk after extraction. No bundle content may be sent to any external service other than the configured LLM provider. Session data must be discarded when the session ends (browser tab close, explicit reset, or server restart). The server must expose a `DELETE /api/sessions/{session_id}` endpoint to explicitly clear session data.
   - *Test: After uploading and analyzing a bundle, call DELETE on the session → subsequent requests for that session return 404. No files are written to disk outside of `/tmp` during extraction. No outbound HTTP calls are made to domains other than the configured LLM API endpoint.*

9. **Docker Compose single-command startup.** The entire application (frontend + backend) must start with `docker compose up`. The `docker-compose.yml` must use a `.env` file for configuration. A `.env.example` file must be provided with placeholder values for all required environment variables (LLM API keys, provider selection, model names).
   - *Test: Clone repo, copy `.env.example` to `.env`, fill in API key, run `docker compose up` → application is accessible at `http://localhost:3000` (or configured port) within 60 seconds. `.env.example` exists and contains placeholders for `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.*

10. **Error handling for LLM failures.** If the LLM API call fails (network error, rate limit, invalid API key, context length exceeded), the system must return a structured error to the frontend with a human-readable message. The frontend must display the error inline (not as a browser alert or silent failure). The system must not crash or leave the session in an inconsistent state.
    - *Test: Configure an invalid API key → upload and analyze → frontend displays an error message containing "API" or "key" or "authentication." Simulate a network timeout → frontend displays an error message. Session remains usable after the error (user can retry).*

11. **Repository quality and documentation.** The repository must include: (a) a `README.md` with project description, setup instructions (prerequisites, env configuration, docker compose up), usage walkthrough, and architecture overview; (b) a `MY_APPROACH_AND_THOUGHTS.md` file of 500 words or fewer describing the technical approach; (c) a `.env.example` with all required environment variables; (d) no dead code, commented-out blocks, or unedited boilerplate.
    - *Test: `README.md` exists and contains the strings "docker compose", "env", and "setup" (case-insensitive). `MY_APPROACH_AND_THOUGHTS.md` exists and word count ≤ 500. `.env.example` exists and contains `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`. No files contain `TODO` or `FIXME` comments (grep check).*

12. **LLM call observability via structured logging.** Every LLM API call (analysis and chat) must emit a structured JSON log entry to stdout containing: `timestamp`, `session_id`, `call_type` ("analyze" or "chat"), `provider` ("anthropic" or "openai"), `model`, `input_tokens`, `output_tokens`, `latency_ms`, and `status` ("success" or "error"). Logs must be visible in `docker compose logs`. No bundle content may appear in log entries (GR-6 compliance).
    - *Test: Trigger an analysis request → stdout contains a JSON log line with all required fields. Trigger a chat request → stdout contains a JSON log line with all required fields. No log entry contains bundle file content (grep for known bundle file paths in log output returns zero matches).*

### Stretch (nice to have)

1. **Severity-based report filtering.** The frontend allows the user to filter the diagnostic report by severity level (show only critical, show critical + warning, show all). Default view shows all findings sorted by severity.

2. **Bundle comparison.** Upload two bundles from different points in time for the same cluster. The system produces a diff-oriented analysis highlighting what changed between them and whether the changes correlate with new or resolved issues.

3. **Export report as Markdown.** A "Download Report" button that exports the structured diagnostic report as a formatted Markdown file.

4. **Confidence scoring.** Each finding includes a confidence indicator (high / medium / low) based on how much corroborating evidence exists across signal types.

5. **Source citing for findings.** Each finding in the diagnostic report includes a `sources` field: a list of `{ file_path: str, excerpt: str }` objects pointing to the specific bundle files and relevant text excerpts that support the finding. In chat responses, the LLM similarly cites which bundle files it is drawing from. The frontend renders source citations as expandable references beneath each finding.
   - *Test: Given a mocked LLM response with source citations, the report JSON contains a `sources` array on each finding. Each source has a `file_path` that exists in the bundle manifest and a non-empty `excerpt` string. Frontend renders at least one source citation per finding.*

### Out of Scope

- **Kubernetes cluster provisioning, management, or setup tooling.** The system analyzes bundles — it does not interact with live clusters.
- **Support bundle generation tooling.** Bundles are provided pre-generated by the user.
- **User authentication, accounts, sessions persistence, or multi-tenancy.** Single-user prototype. No login, no saved history.
- **Billing, usage tracking, or metering.** No cost tracking for LLM API usage.
- **Custom support bundle spec parsing or validation.** The system parses standard Troubleshoot bundle directory structures but does not parse or validate the YAML spec that generated the bundle.
- **Persistent storage of any kind.** No database, no file-based state, no caching across sessions.
- **Automated remediation or kubectl command execution.** The system recommends fixes — it does not execute them.
- **Support for non-Troubleshoot archive formats.** Only `.tar.gz` bundles from the Troubleshoot tool are supported.
- **Mobile-responsive design.** Desktop-only is acceptable for this prototype.
- **Browser compatibility beyond modern Chrome/Firefox.** No IE, Safari, or Edge testing required.
- **End-to-end or integration test suites requiring a running LLM.** Tests that exercise LLM behavior must use mocked/stubbed provider responses.
- **External observability platforms (Langfuse, LangSmith, Datadog LLM Monitoring).** Observability is structured logging to stdout only. ADR: in production, a self-hosted Langfuse deployment would enable full prompt/response tracing while maintaining data sovereignty (GR-6). Log this decision in the project's ADR log.

## System Overview

The system is a two-container web application:

**Frontend (React SPA):** Handles the three-phase user flow: (1) bundle upload with drag-and-drop, (2) streaming report display with structured findings, (3) chat interface for follow-up investigation. Communicates with the backend via REST + SSE. State managed with React useState/useReducer — no external state library.

**Backend (FastAPI):** Exposes three main endpoints: upload, analyze, and chat. The upload endpoint extracts the tar.gz in memory, classifies files by signal type, and creates an in-memory session. The analyze endpoint assembles the classified content into an LLM prompt (with truncation if needed), streams the structured report back via SSE. The chat endpoint maintains conversation history, provides the report and bundle manifest as context, and supports tool-use (function calling) so the LLM can request specific file contents on demand.

**LLM Provider Interface:** A Python abstract class with two implementations (Anthropic, OpenAI). Exposes `analyze(context) -> AsyncIterator[str]` and `chat(messages, tools) -> AsyncIterator[str]`. Selected at startup via environment variable.

**Session Store:** An in-memory dictionary mapping session IDs to session objects (extracted bundle content, manifest, report, chat history). No persistence. Cleared on session delete or server restart.

## Data Model

All entities are in-memory (no database). Represented as Python dataclasses or Pydantic models.

- **Session** — `session_id: str`, `created_at: datetime`, `bundle_manifest: BundleManifest`, `extracted_files: dict[str, bytes]`, `classified_signals: dict[SignalType, list[BundleFile]]`, `report: DiagnosticReport | None`, `chat_history: list[ChatMessage]`

- **BundleManifest** — `total_files: int`, `total_size_bytes: int`, `files: list[BundleFile]`

- **BundleFile** — `path: str`, `size_bytes: int`, `signal_type: SignalType`

- **SignalType** — Enum: `pod_logs`, `cluster_info`, `resource_definitions`, `events`, `node_status`, `other`

- **DiagnosticReport** — `executive_summary: str`, `findings: list[Finding]`, `signal_types_analyzed: list[SignalType]`, `truncation_notes: str | None`

- **Finding** — `severity: Severity`, `title: str`, `description: str`, `root_cause: str`, `remediation: str`, `source_signals: list[SignalType]`, `sources: list[SourceCitation] | None` *(sources populated only when stretch goal 5 is implemented)*

- **SourceCitation** *(stretch)* — `file_path: str`, `excerpt: str`

- **Severity** — Enum: `critical`, `warning`, `info`

- **ChatMessage** — `role: str` (user | assistant | tool), `content: str`, `tool_call: ToolCall | None`, `timestamp: datetime`

- **ToolCall** — `name: str` (always `get_file_contents`), `arguments: dict` (contains `file_path: str`), `result: str | None`

Relationships: A Session has one BundleManifest, one optional DiagnosticReport, and many ChatMessages. A BundleManifest has many BundleFiles. A DiagnosticReport has many Findings. A ChatMessage may have one ToolCall.

## API / Interface Contracts

### REST + SSE Endpoints

**`POST /api/upload`**
- Content-Type: `multipart/form-data`
- Body: `file` (the .tar.gz bundle)
- Response 200: `{ "session_id": "uuid", "manifest": { "total_files": int, "total_size_bytes": int, "files": [{ "path": str, "size_bytes": int, "signal_type": str }] } }`
- Response 400: `{ "error": "Invalid file format. Expected a .tar.gz archive." }`
- Response 413: `{ "error": "File exceeds maximum upload size of 500MB." }`

**`GET /api/analyze/{session_id}`**
- Response: SSE stream (`text/event-stream`)
- Events: `data: { "type": "chunk", "content": "..." }` during streaming, `data: { "type": "report", "report": { DiagnosticReport JSON } }` on completion, `data: { "type": "error", "message": "..." }` on failure.
- Response 404: `{ "error": "Session not found." }`

**`POST /api/chat/{session_id}`**
- Content-Type: `application/json`
- Body: `{ "message": "user's question" }`
- Response: SSE stream (`text/event-stream`)
- Events: `data: { "type": "chunk", "content": "..." }` during streaming, `data: { "type": "tool_use", "name": "get_file_contents", "file_path": "..." }` when the LLM requests a file, `data: { "type": "done" }` on completion, `data: { "type": "error", "message": "..." }` on failure.
- Response 404: `{ "error": "Session not found." }`

**`DELETE /api/sessions/{session_id}`**
- Response 200: `{ "deleted": true }`
- Response 404: `{ "error": "Session not found." }`

### LLM Provider Interface (internal)

```python
class LLMProvider(ABC):
    async def analyze(self, context: AnalysisContext) -> AsyncIterator[str]: ...
    async def chat(self, messages: list[ChatMessage], tools: list[ToolDef], tool_handler: Callable) -> AsyncIterator[str]: ...
```

### Tool Definition (for chat file retrieval)

```json
{
  "name": "get_file_contents",
  "description": "Retrieve the contents of a specific file from the uploaded support bundle.",
  "parameters": {
    "type": "object",
    "properties": {
      "file_path": {
        "type": "string",
        "description": "The path of the file within the bundle, as listed in the bundle manifest."
      }
    },
    "required": ["file_path"]
  }
}
```

## Quality Requirements

- **Test coverage target**: ≥80% line coverage overall. ≥95% coverage for bundle parsing, signal classification, and context truncation logic. LLM interactions tested with mocked/stubbed provider responses.
- **Performance**: Bundle upload and extraction completes in <10 seconds for bundles ≤100MB. First SSE event from the analysis stream arrives within 5 seconds of request. Chat responses begin streaming within 3 seconds.
- **Security**: No bundle content persisted to disk beyond extraction. No bundle content sent to services other than the configured LLM provider. No API keys or secrets in the codebase — `.env.example` with placeholders only. File upload validated: type check (.tar.gz), size check (≤500MB), path traversal prevention during extraction.
- **Accessibility**: Not a priority for this prototype. Semantic HTML and basic keyboard navigation are sufficient.

## Known Constraints

- **Development is agentic** (Claude Code with TDD workflow). All requirements must be testable. The agent operates via the CLAUDE.md bootstrap protocol.
- **This is a hiring project for Replicated.** The evaluator will clone the repo, run `docker compose up`, upload a real support bundle, and judge the quality of analysis, code, and product thinking. Repo presentation matters.
- **No persistent storage.** All data is session-scoped and in-memory. This is a deliberate constraint (GR-6), not a shortcut.
- **LLM API key required.** The evaluator must supply their own API key. The system must fail gracefully with a clear message if no key is configured.
- **Bundle structure varies.** Troubleshoot bundles follow common directory conventions but are not guaranteed to have all signal types. The system must handle partial bundles gracefully — analyze what's present, skip what's missing.
- **LLM responses are non-deterministic.** Tests that assert on LLM output must use mocked responses. Integration tests with a live LLM are out of scope.
- **Demo video is out of scope for the agent.** The user will produce the 2-minute demo independently.

## Reference

- [Troubleshoot.sh](https://troubleshoot.sh) — Troubleshoot tool documentation and bundle format reference
- [Replicated docs: Support Bundles](https://docs.replicated.com/vendor/support-bundle-overview) — Vendor-side documentation
- [Support bundle directory structure](https://troubleshoot.sh/docs/support-bundle/overview/) — Expected paths and file types within a bundle
- [Anthropic function calling docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — Tool use for chat file retrieval
- [OpenAI function calling docs](https://platform.openai.com/docs/guides/function-calling) — Tool use for chat file retrieval
- `replicated_hiring_project_3.pdf` — Original hiring challenge brief (in project repo)
