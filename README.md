# Project Template — Claude Code Bootstrap

A standardized project template for bootstrapping production-quality projects with Claude Code.

## Quick Start

### 1. Extract golden requirements

Open your **"Golden Requirements"** Claude Project. Paste your raw source materials (assignment brief, client spec, challenge description — whatever you have). It extracts the non-negotiable constraints into a `GOLDEN.md`.

### 2. Generate your PRD

Open your **"PRD Workshop"** Claude Project. Describe your idea and provide your `GOLDEN.md` as a reference. The interviewer will walk you through generating a complete `PRD.md` that respects every golden constraint.

### 3. Create your repo

Click **"Use this template"** on GitHub to create a new repository from this template.

### 4. Add your files

Copy both `GOLDEN.md` and `PRD.md` into the repo root.

### 5. Start Claude Code

Open the project directory in Claude Code. It will detect the bootstrap trigger (`CLAUDE.md` + `PRD.md`, no `ARCHITECTURE.md`) and begin the phased initialization:

- **Phase 0**: Init & plan — git setup, stack confirmation, planning gate
- **Phase 1**: Generate module files — ARCHITECTURE.md, IMPLEMENTATION.md, DECISIONS.md, TESTING.md
- **Phase 2**: Scaffold — directory structure, dependencies, tooling
- **Phase 3**: Validation checkpoint — final review before coding begins

Each phase ends with a checkpoint and a fresh session to manage context.

## What's Included

```
├── CLAUDE.md                        # Agent operating manual
├── .claude/
│   └── commands/
│       ├── status.md                # /status — current task + progress
│       ├── next.md                  # /next — plan the next task
│       ├── review.md                # /review — self-review against Definition of Done
│       ├── checkpoint.md            # /checkpoint — write session state
│       ├── recover.md               # /recover — context recovery for new sessions
│       └── stuck.md                 # /stuck — error recovery protocol
├── README.md                        # This file
├── PRD.md                           # ← You add this (via PRD Workshop)
└── GOLDEN.md                        # ← You add this (via Golden Requirements)
```

## What Gets Generated

After bootstrap, Claude Code produces:

- `ARCHITECTURE.md` — system design, components, data flow
- `IMPLEMENTATION.md` — sequenced tasks with acceptance criteria
- `DECISIONS.md` — architecture decision records
- `TESTING.md` — test strategy and conventions
- Project scaffold (directories, dependencies, tooling)

## Slash Commands

| Command | What it does |
|---|---|
| `/status` | Report current task, progress, and blockers |
| `/next` | Pick up and plan the next TODO task |
| `/review` | Self-review current work against Definition of Done |
| `/checkpoint` | Write a session checkpoint for clean handoffs |
| `/recover` | Full context recovery when starting a new session |
| `/stuck` | Stop thrashing, revert, and present the problem |

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- A `GOLDEN.md` generated via the Golden Requirements Claude Project (from your raw source materials)
- A `PRD.md` generated via the PRD Workshop Claude Project (referencing your GOLDEN.md)
