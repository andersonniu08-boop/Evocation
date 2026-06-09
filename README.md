# 🐕 MemoryDog

**A memory-augmented coding agent that gets better the longer you work with it.**

Unlike stateless coding agents, MemoryDog remembers previous conversations, design decisions, bugs, and project history across sessions. It combines persistent memory with hybrid retrieval, workspace-aware ranking, and an instinct engine for reusable behavioral modules — all inside VS Code.

---

## Quick Start (VS Code)

```bash
# 1. Install the extension
code --install-extension memorydog-0.1.0.vsix

# 2. Start PostgreSQL + pgvector
docker compose up -d

# 3. Pull the embedding model
ollama pull nomic-embed-text

# 4. Open VS Code, click the 🐕 icon in the Activity Bar
# 5. Enter your API key in the Chat panel
# 6. Start chatting
```

---

## How It Works

```
Session 1:  "Remember that we chose Textual because it supports multi-pane layouts."
Session 2:  "Why did we choose Textual?"
            → "According to my memory, we chose Textual because it supports multi-pane layouts."
```

MemoryDog stores facts from conversations, embeds them locally via Ollama, retrieves them with hybrid search, and injects them into the LLM context — automatically, across sessions.

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ VS Code Extension (TypeScript)                       │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Chat     │  │ Memory   │  │ Instinct Viewer   │  │
│  │ Panel    │  │ Browser  │  │                   │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │             │                │               │
│       └─────────────┼────────────────┘               │
│                     │                                │
│            JSON-RPC over stdin/stdout                │
│                     │                                │
│  ┌──────────────────┴────────────────────────────┐  │
│  │ memorydog-core (Python package, zero UI)      │  │
│  │                                                │  │
│  │  Agent Loop  │  Tools (x7)  │  Provider        │  │
│  │  Memory CRUD │  Retrieval   │  Ranking         │  │
│  │  Instincts   │  Embeddings  │  DB Layer        │  │
│  └──────────────────┬─────────────────────────────┘  │
│                     │ asyncpg                         │
│                     ▼                                 │
│  ┌──────────────────────────────────────────────────┐│
│  │ PostgreSQL 16 + pgvector                          ││
│  │ 5 tables, HNSW vector index, GIN full-text search ││
│  └──────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────┘
```

**Zero duplication.** The VS Code extension, CLI/TUI, and any future frontend all import the same `core/` Python package.

---

## Memory Pipeline

```
User Message
    │
    ▼
Instinct Match → Memory Retrieval → Context Build → LLM Call → Response
    │                  │                                  │
    │                  │                                  ├── Tool execution
    │                  │                                  └── Memory extraction
    │                  │                                         │
    │                  │                                    Embed & Store
    │                  │
    │           Hybrid Search:
    │           • Vector (pgvector HNSW cosine)
    │           • BM25 keyword (PostgreSQL FTS)
    │           • UNION → formula rank → top 5
    │
    TOML keyword triggers
    → retrieval bias
    → prompt injection
```

### Hybrid Ranking Formula

```
Score = 0.25·V + 0.20·B + 0.15·R + 0.15·I + 0.20·W + 0.05·F
```

| Term | Weight | Definition |
|------|--------|------------|
| **V** Vector | 0.25 | Cosine similarity via pgvector HNSW |
| **B** BM25 | 0.20 | PostgreSQL full-text search ranking |
| **R** Recency | 0.15 | `e^(-0.01 × days)` |
| **I** Importance | 0.15 | `importance × decay_factor` |
| **W** Workspace | 0.20 | Same workspace → 2.0×, different → 1.0× |
| **F** Frequency | 0.05 | Logistic sigmoid of access count |

---

## VS Code Extension

The extension provides four panels in the MemoryDog sidebar:

| Panel | Purpose |
|-------|---------|
| **Chat** | Full conversation with streaming, tool execution, status updates |
| **Memories** | Browse persistent memories, filter by workspace |
| **Instincts** | View loaded instincts from `~/.memorydog/instincts.toml` |
| **Mascot** | Animated CSS dog — idle, sniffing, excited, sleeping |

### Commands

| Command | Action |
|---------|--------|
| `MemoryDog: Focus Chat` | Open the chat panel |
| `MemoryDog: Quick Actions` | Show action picker |
| `MemoryDog: Configure API Key` | Set your provider API key |

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `memorydog.apiKey` | (empty) | LLM provider API key |
| `memorydog.model` | `deepseek/deepseek-chat` | LiteLLM model string |

---

## CLI / TUI

A Textual-based terminal UI is available for development and debugging:

```bash
# Start the TUI
dog chat

# Or with a mock provider (no API key needed)
dog chat --mock

# Check status
dog status

# Interactive config
dog config

# Run the JSON-RPC bridge (used by the VS Code extension)
dog serve

# Manage instincts
dog instinct list
dog instinct edit
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
git clone https://github.com/andersonniu08-boop/MemoryDog.git
cd MemoryDog
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
code --install-extension memorydog-0.1.0.vsix

# Install CLI to PATH (optional)
dog install
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
| LLM Provider | LiteLLM (100+ providers) |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | Ollama + nomic-embed-text (768-dim) |
| DB Driver | asyncpg |
| Config | TOML |
| Testing | pytest (80 tests) |
| Linting | Ruff |

---

## Testing

```bash
pytest tests/                          # 80 tests
ruff check core/ cli/ tests/           # lint
python -m tests.benchmarks.harness --task api_evolution  # benchmarks
```

---

## Project Structure

```
memorydog/
├── core/                  # Shared Python library (zero UI)
│   ├── agent_loop.py      # Core execution loop
│   ├── tools.py           # 7 tools
│   ├── provider.py        # LiteLLM / MockProvider
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
│   │   └── webview/       # Chat, memory, instinct, dog HTML
│   └── package.json
├── migrations/
│   └── 001_init.sql       # 5-table schema
├── tests/                 # 80 tests
├── docker-compose.yml
└── pyproject.toml
```

---

## License

MIT
