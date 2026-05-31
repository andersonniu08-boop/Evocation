# AGENTS.md — MemoryDog Development Guidelines

## Architecture

```
core/                MemoryDog Core — shared library, zero UI
  agent_loop.py      Core execution loop
  tools.py           All 7 tools (read, write, edit, bash, glob, grep, memory_search)
  provider.py        LiteLLM wrapper
  memory.py          Memory CRUD, extraction, retrieval
  retrieval.py       Hybrid retrieval queries
  ranking.py         Ranking formula
  instincts.py       TOML loader, activation, bias
  db.py              PostgreSQL connection, queries
  context.py         Prompt construction

cli/                 Textual TUI frontend (imports core)
  main.py            Entry point (dog chat, dog config)
  app.py             Textual app bootstrap
  ui/chat.py         Chat screen
  ui/widgets.py      Custom widgets

vscode/              VS Code extension (TypeScript)
  src/extension.ts   Extension entry, terminal + webview
  src/webview/       Sidebar panels (HTML/JS)
  assets/dog/        Animated mascot assets
```

**Both frontends import `core/`.** No duplication of agent logic, memory, retrieval, or instincts.

## Conventions

- Python 3.11+, async where possible
- asyncpg for database (raw SQL, not SQLAlchemy ORM)
- LiteLLM for all LLM calls — never call OpenAI/Anthropic directly
- TOML for config and instincts (tomllib in stdlib)
- Ruff for linting, pytest for testing
- 🐕 Dog persona in status chrome only — never in agent responses to user
- Status messages through `dog_status(message)` helper, not direct print

## MVP Scope

Do not add (yet):
- FastAPI, Flask, or any server
- Redis, message queues, background workers
- Multi-user, auth, API keys
- Memory relations, confidence scoring
- Automatic instinct generation

## Design Spec

Read `docs/specs/2026-05-31-memorydog-mvp.md` before making architectural changes.

## Testing

```bash
pytest tests/
```

## Linting

```bash
ruff check core/ cli/ tests/
```
