# Evocation

**A goal-oriented AI development agent.**

Evocation takes a high-level objective and transforms it into an executable plan: **Goal → Planner → Tasks → Executor**. It combines persistent memory with hybrid retrieval, local LLM support via Ollama, and an autonomous task execution loop — all inside VS Code.

---

## Quick Start (VS Code)

```bash
# 1. Install the extension
code --install-extension evocation-0.1.0.vsix

# 2. Start PostgreSQL + pgvector
docker compose up -d

# 3. Pull the embedding model
ollama pull nomic-embed-text

# 4. Open VS Code, click the ⚡ icon in the Activity Bar
# 5. Pick a model from the dropdown (phi4-mini is default — no API key needed)
# 6. Start chatting
```

---

## How It Works

Evocation stores facts from conversations, embeds them locally via Ollama, retrieves them with hybrid search weighted by structural importance, and injects them into the LLM context — automatically, across sessions. When you provide a goal, the Planner generates a task list and the Executor works through it step by step, running tools autonomously.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ VS Code Extension (TypeScript)                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Editor   │  │ Goals    │  │ Context / Instinct │  │
│  │ Tab      │  │ Panel    │  │ Panels             │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │             │                │               │
│       └─────────────┼────────────────┘               │
│                     │                                │
│            JSON-RPC over stdin/stdout                │
│                     │                                │
│  ┌──────────────────┴────────────────────────────┐  │
│  │ evocation-core (Python package, zero UI)      │  │
│  │                                                │  │
│  │  Executor   │  Planner    │  Provider          │  │
│  │  Memory CRUD│  Retrieval  │  Tools (x7)       │  │
│  │  Instincts  │  Embeddings │  DB Layer          │  │
│  └──────────────────┬─────────────────────────────┘  │
│                     │ asyncpg                         │
│                     ▼                                 │
│  ┌──────────────────────────────────────────────────┐│
│  │ PostgreSQL 16 + pgvector                          ││
│  │ 8 tables, HNSW vector index, GIN full-text search ││
│  └──────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

**Zero duplication.** The VS Code extension, CLI/TUI, and any future frontend all import the same `core/` Python package.

---

## Goal & Task Pipeline

```
Objective → Planner (LLM generates tasks) → Executor (runs tools autonomously) → Tracker (updates progress)
```

### Execution Mode

The Executor iterates through pending tasks. For each task, it asks the LLM which tool to use, executes it, records findings, and evaluates completion. Destructive tools (bash, write, edit) yield for user approval before executing.

```
Task → LLM decides tool → Execute → Record findings → Evaluate
   ↑                                                    ↓
   └────────── next task (if complete) ─────────────────┘
```

### Planning

Provide a goal objective and the Planner module generates a structured task list:

```json
[
  {"description": "Create User model with password hashing", "order": 1},
  {"description": "Add login endpoint POST /auth/login", "order": 2},
  {"description": "Add JWT token generation and validation", "order": 3}
]
```

### Task Tracking

- **Goals**: title, objective, status (pending/in_progress/completed/failed), progress %
- **Tasks**: description, order, status, findings, notes, timestamps
- **Progress**: `{ total: 7, completed: 2, failed: 1, percentage: 29 }`

---

## Memory System

### Hybrid Ranking

```
Score = 0.25·V + 0.20·B + 0.15·R + 0.15·I + 0.20·W + 0.05·F
```

| Term | Weight | Definition |
|------|--------|------------|
| **V** Vector | 0.25 | Cosine similarity via pgvector HNSW |
| **B** BM25 | 0.20 | PostgreSQL full-text search ranking |
| **R** Recency | 0.15 | `e^(-0.01 × days)` |
| **I** Importance | 0.15 | `importance × decay_factor` |
| **W** Workspace | 0.20 | Same workspace → 2.0× boost |
| **F** Frequency | 0.05 | Logistic sigmoid of access count |

### Structural Priority

Goal-oriented memory types receive relevance multipliers in retrieval:

| Memory Type | Multiplier | Purpose |
|-------------|-----------|---------|
| `past_failure` | 1.30× | Avoid repeating mistakes |
| `plan_architecture` | 1.25× | Architectural decisions |
| `goal_definition` | 1.25× | Project-level goals |
| `bug` | 1.15× | Bug history warnings |
| `design_decision` | 1.10× | Technology choices |
| `conversation` | 1.00× | General context (baseline) |

### Context Formatting

Memories are grouped under structured markdown headers:
```
### Past Failures to Avoid
- Race condition in the task queue worker

### Relevant Architecture
- Use hexagonal architecture with ports/adapters

### Design Decisions
- Chose pgvector for vector search
```

---

## VS Code Extension

| Panel | Purpose |
|-------|---------|
| **Sessions** | Active conversation sessions, create/open/close |
| **Goals** | Active goals with progress bars and status badges |
| **Context** | Browse persistent memories, filter by workspace |
| **Instincts** | View loaded instincts from `~/.memorydog/instincts.toml` |

### Goal Dashboard

Click a goal to open the dashboard editor tab:
- **Header**: Objective, status badge, progress bar, SVG state indicator
- **Left pane**: Task checklist with status icons (✓/✗), expandable findings
- **Right pane**: Activity feed for tool output and status updates

### State Indicator

A minimalist SVG state indicator shows agent activity: idle (pulsing), thinking (expanding), executing (spinning), success (pop), error (shake). No external assets — 24×24px inline SVG driven by the `BridgeAgentState` machine.

### Commands

| Command | Action |
|---------|--------|
| `Evocation: New Session` | Start a new chat session |
| `Evocation: Open Goal Dashboard` | View goal detail with task list |
| `Evocation: Quick Actions` | Show action picker |
| `Evocation: Configure API Key` | Set your provider API key |

### Local LLM Default

The extension ships with **phi4-mini** as the default model via Ollama. No API key required. Cloud models (DeepSeek, OpenAI, Claude, OpenRouter) are available in the model dropdown — API key field appears only when selected.

---

## CLI / TUI

A Textual-based terminal UI is available for development and debugging:

```bash
evocation                  # Start the TUI with your default model
evocation --mock           # Start with mock provider (no API key)
evocation status           # Check system health
evocation config           # Interactive configuration
evocation serve            # JSON-RPC bridge (used by VS Code extension)
evocation instinct list    # List loaded instincts
```

---

## Instinct System

Instincts are user-defined behavioral modules in `~/.memorydog/instincts.toml`. They activate on keyword triggers and influence retrieval + agent behavior.

```toml
[[instincts]]
name = "Bug Hunter"
triggers = ["bug", "race condition", "deadlock", "fix", "debug", "crash"]
prompt = "When fixing bugs, add a regression test and check similar code."
retrieval_bias = ["bug", "fix", "test", "regression"]
```

Three instincts ship by default: Bug Hunter, AI Evaluation Expert, Recruiter Lens.

---

## Setup (Full)

### Prerequisites

- Python 3.11+
- PostgreSQL 16+ with pgvector
- Ollama
- VS Code 1.85+

### Installation

```bash
git clone https://github.com/andersonniu08-boop/Evocation.git
cd Evocation
pip install -e ".[dev]"
docker compose up -d
ollama pull nomic-embed-text

cd vscode && npm install && npm run compile && npx @vscode/vsce package
code --install-extension evocation-0.1.0.vsix
```

### Verify

```bash
evocation status
```

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ |
| VS Code Extension | TypeScript |
| LLM Provider | Ollama (local) + LiteLLM (cloud) |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | Ollama + nomic-embed-text (768-dim) |
| DB Driver | asyncpg |
| Bridge | JSON-RPC 2.0 over subprocess stdin/stdout |
| Config | TOML (~/.memorydog/) |
| Testing | pytest (141 tests) |
| Linting | Ruff |

---

## Project Structure

```
evocation/
├── core/                  # Shared Python library (zero UI)
│   ├── executor.py        # Autonomous task execution engine
│   ├── agent_loop.py      # Core chat execution loop
│   ├── planning.py        # Planner — LLM task generation
│   ├── tools.py           # 7 tools (read, write, edit, bash, glob, grep)
│   ├── provider.py        # Ollama + LiteLLM providers
│   ├── memory.py          # CRUD, extraction, embeddings
│   ├── retrieval.py       # Hybrid vector + FTS + budget + multipliers
│   ├── ranking.py         # 6-term scoring formula
│   ├── instincts.py       # TOML loader, trigger matching
│   ├── bridge.py          # JSON-RPC server for VS Code
│   ├── db.py              # asyncpg pool, auto-migration
│   ├── context.py         # Prompt construction
│   └── config.py          # TOML config with local LLM support
├── cli/                   # Textual TUI (secondary interface)
│   ├── main.py            # evocation CLI entry point
│   └── ui/                # Chat screen, widgets
├── vscode/                # VS Code extension (primary interface)
│   ├── src/
│   │   ├── extension.ts   # Activation, providers, commands
│   │   ├── bridge.ts      # JSON-RPC client
│   │   └── webview/       # chat, goals, dashboard, memory, instinct HTML
│   └── package.json
├── migrations/
│   └── 001_init.sql       # 8-table schema (memories, goals, tasks, etc.)
├── tests/                 # 141 tests
├── DESIGN.md              # UI/UX architecture
├── PLAN.md                # Implementation roadmap
├── docker-compose.yml
└── pyproject.toml
```

---

## License

MIT
