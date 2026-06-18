# AGENTS.md — Evocation Development Guidelines

## Project Identity

Evocation is a **goal-oriented AI development agent**. Unlike chat-first coding assistants, Evocation accepts a high-level objective and transforms it into an executable plan: **Goal → Planner → Tasks → Executor → Tracker**.

## Architecture

```
core/                Evocation Core — shared library, zero UI
  agent_loop.py      Autonomous execution loop (plan → execute → track)
  planning.py         Planner module — LLM-driven task decomposition
  tools.py           7 tools (read, write, edit, bash, glob, grep, memory_search)
  provider.py         BaseProvider, OllamaProvider, LiteLLMProvider
  memory.py           Memory CRUD, extraction, embedding, parsing
  retrieval.py        Hybrid vector + FTS retrieval
  ranking.py          Score formula: 0.25V + 0.20B + 0.15R + 0.15I + 0.20W + 0.05F
  instincts.py        TOML loading
  db.py               asyncpg pool, auto-migration
  bridge.py           JSON-RPC bridge for VS Code extension
  config.py           TOML config with local LLM support

cli/                 Textual TUI frontend (imports core)
  main.py            Entry point (dog chat, config, status, install)
  app.py             Textual app bootstrap
  ui/chat.py         Chat screen with live status + streaming
  ui/widgets.py      StatusBar, PlanPanel, DiffPreview, ToolOutput

vscode/              VS Code extension (TypeScript)
  src/extension.ts   Session architecture, commands, sidebar providers
  src/bridge.ts      Bridge client for Python subprocess JSON-RPC
  src/webview/       Editor tab + sidebar panels (HTML/JS)
```

## Core Execution Loop

```
User provides Goal objective
  → Planner generates Task plan (LLM → structured JSON)
  → Executor iterates tasks sequentially
    → Running tools (read, write, bash, etc.)
    → Recording findings
    → Yielding for user approval (destructive operations)
  → Tracker updates progress
  → Goal status reflects reality (pending → in_progress → completed)
```

## Conventions

- Python 3.11+, async where possible
- asyncpg for database (raw SQL, not SQLAlchemy ORM)
- LiteLLM for cloud LLM calls, httpx for local Ollama calls
- TOML for config (tomllib in stdlib)
- Ruff for linting, pytest for testing
- Status messages through `_status(message, callback)`
- BridgeAgentState enum drives all UI state transitions
- Config directory: `~/.memorydog/config.toml`

## Entity Model

| Entity | Source | Description |
|--------|--------|-------------|
| **Goal** | `goals` table | High-level objective with status tracking |
| **Task** | Planner output | JSON plan steps generated from Goal |
| **Session** | `conversations` table | Chat sessions linked to goals via `goal_id` |
| **Memory** | `memories` table | Persistent facts with pgvector embeddings |

## Design Spec

Read `docs/specs/2026-05-31-evocation-mvp.md` for the full design rationale.
Read `PLAN.md` for the implementation roadmap.
Read `DESIGN.md` for the UI/UX architecture.

## Testing

```bash
pytest tests/                          # 125 tests
```

## Linting

```bash
ruff check core/ cli/ tests/
```
