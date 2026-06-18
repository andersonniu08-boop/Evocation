# Evocation

**A goal-oriented AI development agent.**

Evocation takes a high-level objective and transforms it into an executable plan: **Goal → Planner → Tasks → Execution**. It combines persistent memory with hybrid retrieval, local LLM support via Ollama, and a task-oriented execution loop — all inside VS Code.

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

Evocation stores facts from conversations, embeds them locally via Ollama, retrieves them with hybrid search, and injects them into the LLM context — automatically, across sessions. When you provide a goal, the Planner generates a task list and the agent works through it step by step.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ VS Code Extension (TypeScript)                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Editor   │  │ Context  │  │ Instinct Viewer   │  │
│  │ Tab      │  │ Browser  │  │                   │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │             │                │               │
│       └─────────────┼────────────────┘               │
│                     │                                │
│            JSON-RPC over stdin/stdout                │
│                     │                                │
│  ┌──────────────────┴────────────────────────────┐  │
│  │ evocation-core (Python package, zero UI)      │  │
│  │                                                │  │
│  │  Goal Loop  │  Planning   │  Provider          │  │
│  │  Memory CRUD│  Retrieval  │  Tools (x7)       │  │
│  │  Instincts  │  Embeddings │  DB Layer          │  │
│  └──────────────────┬─────────────────────────────┘  │
│                     │ asyncpg                         │
│                     ▼                                 │
│  ┌──────────────────────────────────────────────────┐│
│  │ PostgreSQL 16 + pgvector                          ││
│  │ 6 tables, HNSW vector index, GIN full-text search ││
│  └──────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

**Zero duplication.** The VS Code extension, CLI/TUI, and any future frontend all import the same `core/` Python package.

---

## Goal & Task Pipeline

```
Objective → Planner (LLM generates tasks) → Executor (runs tools) → Tracker (updates progress)
```

### Task Planning

Provide a goal objective and the Planner module generates a structured task list:

```json
[
  {"description": "Create User model with password hashing", "order": 1},
  {"description": "Add login endpoint POST /auth/login", "order": 2},
  {"description": "Add JWT token generation and validation", "order": 3}
]
```

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

---

## VS Code Extension

The extension provides a session-first sidebar experience:

| Panel | Purpose |
|-------|---------|
| **Sessions** | Active conversation sessions, create/open/close |
| **Context** | Browse persistent memories, filter by workspace |
| **Instincts** | View loaded instincts from `~/.memorydog/instincts.toml` |

### State Indicator

A minimalist SVG state indicator shows agent activity: idle (pulsing), thinking (expanding), executing (spinning), success (pop), error (shake). No external assets — 24×24px inline SVG driven by the `BridgeAgentState` machine.

### Commands

| Command | Action |
|---------|--------|
| `Evocation: New Session` | Start a new chat session |
| `Evocation: Quick Actions` | Show action picker |
| `Evocation: Configure API Key` | Set your provider API key |

### Local LLM Default

The extension ships with **phi4-mini** as the default model via Ollama. No API key required. Cloud models (DeepSeek, OpenAI, Claude) are available in the model dropdown — API key field appears only when selected.

---

## CLI / TUI

A Textual-based terminal UI is available for development and debugging:

```bash
dog chat              # Start the TUI with your default model
dog chat --mock       # Start with mock provider (no API key)
dog status            # Check system health
dog config            # Interactive configuration
dog serve             # JSON-RPC bridge (used by VS Code extension)
dog instinct list     # List loaded instincts
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
# Clone and install Python package
git clone https://github.com/andersonniu08-boop/Evocation.git
cd Evocation
pip install -e ".[dev]"

# Start database
docker compose up -d

# Pull embedding model
ollama pull nomic-embed-text

# Build VS Code extension
cd vscode
npm install
npm run compile
npx @vscode/vsce package

# Install extension
code --install-extension evocation-0.1.0.vsix
```

### Verify

```bash
dog status
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
| Config | TOML |
| Testing | pytest (125 tests) |
| Linting | Ruff |

---

## Testing

```bash
pytest tests/                          # 125 tests
ruff check core/ cli/ tests/           # lint
```

---

## Project Structure

```
evocation/
├── core/                  # Shared Python library (zero UI)
│   ├── agent_loop.py      # Core execution loop
│   ├── planning.py        # Planner — LLM task generation
│   ├── tools.py           # 7 tools
│   ├── provider.py        # Ollama + LiteLLM providers
│   ├── memory.py          # CRUD, extraction, embeddings
│   ├── retrieval.py       # Hybrid vector + FTS + budget
│   ├── ranking.py         # 6-term formula
│   ├── instincts.py       # TOML loader, triggers
│   ├── bridge.py          # JSON-RPC server for VS Code
│   ├── db.py              # asyncpg pool, migrations
│   ├── context.py         # Prompt construction
│   └── config.py          # TOML config
├── cli/                   # Textual TUI (secondary interface)
│   ├── main.py            # dog chat, config, serve, status
│   └── ui/                # Chat screen, widgets
├── vscode/                # VS Code extension (primary interface)
│   ├── src/
│   │   ├── extension.ts   # Activation, providers
│   │   ├── bridge.ts      # JSON-RPC client
│   │   └── webview/       # Chat, context, instinct HTML
│   └── package.json
├── migrations/
│   └── 001_init.sql       # 6-table schema
├── tests/                 # 125 tests
├── docker-compose.yml
└── pyproject.toml
```

---

## License

MIT
