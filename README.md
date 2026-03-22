# Unravel

AI-powered Kubernetes support bundle analyzer. Upload a [Troubleshoot](https://troubleshoot.sh) support bundle, get a structured diagnostic report, then investigate interactively via chat. Browse past analyses in the session explorer dashboard.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                          Unravel                              │
│                                                               │
│  Session Explorer (landing page)                              │
│  ┌─ Past analyses table ─── Detail panel ──────────────────┐  │
│  │  Search, filter, stats    Notes, metadata, findings     │  │
│  └─────────────────────────────────────────────────────────┘  │
│         ↓ New Analysis              ↓ Open Saved Session      │
├──── Sidebar ────┬──── Main Content ───────────────────────────┤
│                 │                                             │
│  File Explorer  │  Progress Stepper → Diagnostic Report      │
│  (by signal     │  ┌─ Executive Summary ──────────────────┐  │
│   type)         │  │ Event Timeline                       │  │
│  ● Events (12)  │  │ Findings (filterable by severity)    │  │
│  ● Pod Logs (8) │  │ Investigation Chat                   │  │
│  ● Cluster (4)  │  │   with suggested questions           │  │
│                 │  └──────────────────────────────────────┘  │
├─────────────────┴────────────────────────────────────────────┤
│  File Viewer (slide-over panel)                              │
└──────────────────────────────────────────────────────────────┘

┌─────────────────────┐       ┌──────────────────────────────┐
│  React SPA (:3000)  │──────▶│  FastAPI Backend (:8000)     │
│                     │  API  │                              │
│  Explorer → Upload  │  SSE  │  Bundle Parser               │
│  → Report → Chat    │◀──────│  Signal Classifier           │
│                     │       │  Context Assembler            │
└─────────────────────┘       │  LLM Provider (Anthropic/    │
                              │    OpenAI)                    │
                              │  Session Store (in-memory)    │
                              │  Session Persistence (JSON)   │
                              └──────────────────────────────┘
                                        │
                              ┌─────────▼──────────────────┐
                              │  Docker Volume              │
                              │  /app/data/sessions/        │
                              │  sessions.json + per-session │
                              │  report.json / chat.json     │
                              └──────────────────────────────┘
```

**Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
**Backend**: Python 3.12 + FastAPI + Pydantic
**LLM**: Anthropic Claude or OpenAI GPT (swappable via env var)

## Setup

### Prerequisites

- Docker and Docker Compose
- An API key for Anthropic or OpenAI

### Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd unravel

# 2. Configure environment
cp .env.example .env
# Edit .env — set LLM_PROVIDER and your API key

# 3. Start
docker compose up
```

The app will be available at **http://localhost:3000**.

> **Note**: The Docker image is ~700MB due to the bundled sentence-transformers embedding model (PyTorch + all-MiniLM-L6-v2). The first `docker compose build` will take longer than usual while the model is downloaded into the image. Subsequent builds are cached.

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | If provider=anthropic | Your Anthropic API key |
| `OPENAI_API_KEY` | If provider=openai | Your OpenAI API key |
| `ANTHROPIC_MODEL` | No | Override model (default: `claude-sonnet-4-20250514`) |
| `OPENAI_MODEL` | No | Override model (default: `gpt-4o`) |
| `RAG_CHUNK_SIZE` | No | Embedding chunk size in tokens (default: `512`) |
| `RAG_CHUNK_OVERLAP` | No | Chunk overlap in tokens (default: `50`) |
| `EVAL_THRESHOLD` | No | Minimum coverage score for quality eval (default: `0.7`) |
| `SESSION_DATA_DIR` | No | Override session history storage path (default: `/app/data/sessions`) |

## Usage

1. **Explore** the session explorer dashboard — browse past analyses, search by bundle name or cluster, filter by status or severity
2. **Upload** a `.tar.gz` support bundle via drag-and-drop or file picker (click "+ New Analysis")
3. **Watch** the progress stepper as the bundle is extracted, classified by signal type, and sent to the AI for analysis
4. **Review** the diagnostic report: executive summary, event timeline, and findings with severity filtering (critical / warning / info)
5. **Browse** bundle files in the sidebar file explorer, grouped by signal type — click any file to view its contents in a slide-over panel
6. **Investigate** via chat — pick a suggested follow-up question or ask your own; the AI retrieves bundle files on demand
7. **Export** the full report as Markdown
8. **Return** to the explorer — your analysis is saved and can be re-opened later with the full report and chat transcript

Session history is persisted to a Docker volume and survives container restarts (`docker compose down`). Use `docker compose down -v` to clear all session data.

## How It Works

1. **Bundle Parsing**: Extracts the tar.gz in memory, validates format, prevents path traversal
2. **Signal Classification**: Categorizes files by path patterns into 5 signal types (pod logs, events, cluster info, resource definitions, node status). The sidebar file explorer groups files by these types so you can browse the raw data
3. **RAG Pipeline**: After classification, files are chunked using content-type-aware strategies (per-event for JSON, per-document for YAML, windowed for logs) and embedded locally using `all-MiniLM-L6-v2` into a session-scoped ChromaDB collection. This enables semantic retrieval during analysis and chat
4. **Event Timeline Extraction**: Kubernetes events are parsed and displayed chronologically with severity indicators, giving a quick view of what happened and when
5. **Context Assembly**: Diagnostic queries retrieve the most relevant chunks via semantic search, then content is prioritized and truncated to fit the LLM context window (~100K tokens)
6. **LLM Analysis**: Streams a structured diagnostic report via SSE with findings, root causes, and remediations (with copy-to-clipboard on each remediation). A quality evaluator checks coverage and citation accuracy after generation
7. **Interactive Chat**: Follow-up investigation with two tools — `search_bundle` for semantic retrieval of relevant chunks, and `get_file_contents` for full file access. Suggested follow-up questions are generated from the report findings to help guide the investigation

Raw bundle data is held in memory during active analysis. Completed analysis results (reports, findings, chat transcripts, and extracted metadata) are persisted to a Docker volume as JSON files for the session explorer.

## Development

### Backend

```bash
cd src/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

### Frontend

```bash
cd src/frontend
npm install
npm test
npm run dev  # Dev server on :3000
```

## Project Structure

```
├── docker-compose.yml
├── .env.example
├── src/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/          # FastAPI routes
│   │   │   ├── analysis/     # Context assembly, chat engine
│   │   │   ├── bundle/       # Parser, signal classifier, chunker
│   │   │   ├── evals/        # Programmatic quality evaluator
│   │   │   ├── llm/          # Provider interface + implementations
│   │   │   ├── logging/      # Structured LLM call logger
│   │   │   ├── models/       # Pydantic schemas
│   │   │   ├── rag/          # Embedder (ChromaDB) + retriever
│   │   │   └── sessions/     # In-memory store + JSON persistence
│   │   └── tests/
│   └── frontend/
│       └── src/
│           ├── components/    # Explorer, Upload, Report, Chat phases
│           │   ├── FileExplorer.tsx   # Sidebar file browser by signal type
│           │   ├── FileViewer.tsx     # Slide-over panel for file contents
│           │   └── Timeline.tsx       # Chronological event timeline
│           ├── hooks/         # SSE streaming hook
│           ├── utils/         # Markdown export helper
│           └── types/         # TypeScript types
```
