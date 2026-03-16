# Unravel

AI-powered Kubernetes support bundle analyzer. Upload a [Troubleshoot](https://troubleshoot.sh) support bundle, get a structured diagnostic report, then investigate interactively via chat.

## Architecture

```
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
2. **Review** the AI-generated diagnostic report with findings sorted by severity
3. **Chat** to investigate further — the AI can retrieve specific files from the bundle on demand

## How It Works

1. **Bundle Parsing**: Extracts the tar.gz in memory, validates format, prevents path traversal
2. **Signal Classification**: Categorizes files by path patterns into 5 signal types (pod logs, events, cluster info, resource definitions, node status)
3. **Context Assembly**: Prioritizes and truncates content to fit the LLM context window (~100K tokens). Priority: events > pod logs > cluster info > resource definitions > node status
4. **LLM Analysis**: Streams a structured diagnostic report via SSE with findings, root causes, and remediations
5. **Interactive Chat**: Follow-up investigation with tool-use — the LLM can request specific bundle files via `get_file_contents`

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
│           ├── hooks/         # SSE streaming hook
│           └── types/         # TypeScript types
```
