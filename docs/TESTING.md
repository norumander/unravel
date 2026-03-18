# TESTING.md

## Test Commands

### Backend (Python / pytest)

```bash
# Run all backend tests
cd src/backend && python -m pytest tests/ -v

# Run a single test file
cd src/backend && python -m pytest tests/test_classifier.py -v

# Run with coverage
cd src/backend && python -m pytest tests/ --cov=app --cov-report=term-missing

# Run only unit tests (fast)
cd src/backend && python -m pytest tests/unit/ -v

# Run only integration tests (requires app setup)
cd src/backend && python -m pytest tests/integration/ -v
```

### Frontend (TypeScript / Vitest)

```bash
# Run all frontend tests
cd src/frontend && npm test

# Run with coverage
cd src/frontend && npm run test:coverage

# Run in watch mode (development)
cd src/frontend && npm run test:watch
```

## Strategy

### Unit Tests
- **Scope**: Individual functions and classes in isolation.
- **Coverage target**: ≥95% for bundle parser, signal classifier, context truncation. ≥80% overall.
- **Speed**: Each test <100ms. Full unit suite <30s.
- **Mocking**: Mock at boundaries only (LLM SDKs, network). Never mock the thing under test.

### Integration Tests
- **Scope**: API endpoints via httpx TestClient (backend), component rendering with mocked API (frontend).
- **Backend**: Test full request/response cycle for each endpoint. Use mocked LLM providers.
- **Frontend**: Test component state transitions with mocked SSE streams.
- **No live LLM calls**: All LLM interactions use mocked/stubbed responses.

### AI Output Boundary Tests

The most critical test surface in an LLM-powered application is the **boundary between unpredictable AI output and the application's type system**. The LLM returns free-form JSON that must conform to our Pydantic schemas, but it regularly produces responses that are valid JSON yet violate the schema in subtle ways.

**What we test at this boundary:**

- **Invented enum values** (`TestSanitizeSignalTypes`): LLMs frequently produce signal type strings that don't exist in our `SignalType` enum (e.g., `node_conditions`, `pod_status`, `deployment_health`). The sanitizer normalizes these to `"other"` before Pydantic validation. Without this, the entire report would be rejected over a single bad enum value. Tests cover: valid types pass through, unknown types become `"other"`, missing keys tolerated, invalid JSON passed through for downstream handling.

- **Malformed JSON** (`TestAnalyzeInvalidJson`): The LLM may return incomplete JSON, prose mixed with JSON, or truncated output. Integration tests verify the error is surfaced to the user rather than crashing.

- **Markdown-wrapped JSON** (`TestAnalyzeMarkdownFences`): LLMs commonly wrap JSON in ` ```json ``` ` fences despite being told not to. The fence stripper handles this transparently.

- **Full integration path** (`TestAnalyzeSignalSanitization`): Tests the complete chain — LLM returns JSON with invented signal types → sanitizer normalizes → Pydantic validates → client receives a valid report. This is the test that would have caught the production bug where reports failed to parse due to `node_conditions`.

**Design principle**: The application must never fail because the LLM was "slightly creative" with its output. Tests verify graceful degradation at every point where AI output enters the type system.

### What We Don't Test
- Live LLM API calls (non-deterministic, requires API key)
- Docker Compose orchestration (manual verification)
- Browser-specific behavior (desktop Chrome/Firefox only, manual verification)
- CSS/visual layout (no visual regression tests)

## Coverage Targets

| Scope | Target | Rationale |
|---|---|---|
| Bundle parser | ≥95% | Core logic, security-critical (path traversal) |
| Signal classifier | ≥95% | Core logic, determines analysis quality |
| Context truncation | ≥95% | Core logic, directly affects LLM results |
| LLM providers | ≥80% | Mocked SDK calls; error paths covered |
| API endpoints | ≥80% | Integration tests cover happy + error paths |
| Session store | ≥90% | Simple but critical CRUD |
| Frontend components | ≥70% | State transitions and rendering; no visual tests |
| Overall | ≥80% | PRD requirement |

## Conventions

### File Structure

```
src/backend/
├── app/                    # Application code
│   ├── models/             # Pydantic models
│   ├── bundle/             # Parser, classifier
│   ├── analysis/           # Context assembler, chat engine
│   ├── llm/                # Provider interface + implementations
│   ├── sessions/           # Session store
│   ├── logging/            # Structured logger
│   └── api/                # FastAPI routes
└── tests/
    ├── unit/               # Unit tests (mirror app/ structure)
    ├── integration/        # API endpoint tests
    ├── fixtures/           # Shared test data (small .tar.gz files, mock responses)
    └── conftest.py         # Shared fixtures

src/frontend/
├── src/
│   ├── components/         # React components
│   ├── hooks/              # Custom hooks
│   ├── types/              # TypeScript types
│   └── utils/              # Utility functions
└── tests/                  # Co-located or in __tests__/
```

### Naming

- Test files: `test_<module>.py` (backend), `<Component>.test.tsx` (frontend)
- Test functions: `test_<action>_<condition>_<expected>`
  - Example: `test_parse_bundle_invalid_format_raises_error`
  - Example: `test_classify_pod_logs_path_returns_pod_logs_type`
- Describe blocks (frontend): `describe('<ComponentName>', () => { ... })`

### Fixtures

- Small synthetic .tar.gz bundles in `tests/fixtures/` for parser/classifier tests
- Mock LLM responses (streaming chunks) as Python constants or JSON files
- pytest fixtures in `conftest.py` for shared setup (test client, mock providers, sample sessions)
- Factory functions preferred over large fixture files for flexibility

### Mocking Rules

- **Mock at boundaries**: LLM SDK clients, HTTP calls, time/clock.
- **Never mock**: The function/class under test, Python stdlib, Pydantic models.
- **LLM mocks must be realistic**: Include streaming chunks, tool_use blocks, token counts, proper finish reasons.
- **Use `unittest.mock.AsyncMock`** for async generators in LLM provider mocks.
- **Backend integration tests**: Use `httpx.AsyncClient` with FastAPI's `TestClient` for async endpoint testing.

### Test Data

- Bundle test fixtures should be minimal (2-5 files, <10KB total) to keep tests fast.
- Include at least one fixture with files in each signal type category.
- Include one fixture with only "other" type files (edge case).
- Include one fixture with path traversal attempt.
- Mock LLM responses should match the actual SDK response format exactly.
