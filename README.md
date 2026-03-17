# Unravel

AI-powered Kubernetes support bundle analyzer. Upload a [Troubleshoot](https://troubleshoot.sh) support bundle, get a structured diagnostic report, then investigate interactively via chat.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                          Unravel                              │
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
│  Upload → Report    │  SSE  │  Bundle Parser               │
│  → Chat             │◀──────│  Signal Classifier           │
│                     │       │  Context Assembler            │
└─────────────────────┘       │  LLM Provider (Anthropic/    │
                              │    OpenAI)                    │
                              │  Session Store (in-memory)    │
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

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` | If provider=anthropic | Your Anthropic API key |
| `OPENAI_API_KEY` | If provider=openai | Your OpenAI API key |
| `ANTHROPIC_MODEL` | No | Override model (default: `claude-sonnet-4-20250514`) |
| `OPENAI_MODEL` | No | Override model (default: `gpt-4o`) |

## Usage

1. **Upload** a `.tar.gz` support bundle via drag-and-drop or file picker
2. **Watch** the progress stepper as the bundle is extracted, classified by signal type, and sent to the AI for analysis
3. **Review** the diagnostic report: executive summary, event timeline, and findings with severity filtering (critical / warning / info)
4. **Browse** bundle files in the sidebar file explorer, grouped by signal type — click any file to view its contents in a slide-over panel
5. **Investigate** via chat — pick a suggested follow-up question or ask your own; the AI retrieves bundle files on demand
6. **Export** the full report as Markdown

## How It Works

1. **Bundle Parsing**: Extracts the tar.gz in memory, validates format, prevents path traversal
2. **Signal Classification**: Categorizes files by path patterns into 5 signal types (pod logs, events, cluster info, resource definitions, node status). The sidebar file explorer groups files by these types so you can browse the raw data
3. **Event Timeline Extraction**: Kubernetes events are parsed and displayed chronologically with severity indicators, giving a quick view of what happened and when
4. **Context Assembly**: Prioritizes and truncates content to fit the LLM context window (~100K tokens). Priority: events > pod logs > cluster info > resource definitions > node status
5. **LLM Analysis**: Streams a structured diagnostic report via SSE with findings, root causes, and remediations (with copy-to-clipboard on each remediation)
6. **Interactive Chat**: Follow-up investigation with tool-use — the LLM can request specific bundle files via `get_file_contents`. Suggested follow-up questions are generated from the report findings to help guide the investigation

All bundle data is held in memory only and never persisted to disk. Sessions are cleared on delete or server restart.

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
│   │   │   ├── bundle/       # Parser, signal classifier
│   │   │   ├── llm/          # Provider interface + implementations
│   │   │   ├── logging/      # Structured LLM call logger
│   │   │   ├── models/       # Pydantic schemas
│   │   │   └── sessions/     # In-memory session store
│   │   └── tests/
│   └── frontend/
│       └── src/
│           ├── components/    # Upload, Report, Chat phases
│           │   ├── FileExplorer.tsx   # Sidebar file browser by signal type
│           │   ├── FileViewer.tsx     # Slide-over panel for file contents
│           │   └── Timeline.tsx       # Chronological event timeline
│           ├── hooks/         # SSE streaming hook
│           ├── utils/         # Markdown export helper
│           └── types/         # TypeScript types
```
