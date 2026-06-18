# Evocation — Design Document

## Product Identity

Evocation is a **goal-oriented AI development agent**. Users provide a high-level objective; Evocation plans, executes, and tracks progress autonomously.

The chat is a means to an end — not the product. The Goal is the primary entity.

## Architecture

### Backend (Python)

```
User → Goal objective
  → Planner (LLM generates Task plan)
  → Executor (iterates tasks, runs tools, records findings)
  → Tracker (updates progress, surfaces blockers)
```

### Frontend (VS Code)

- **Activity Bar icon:** Minimal SVG state indicator (idle, thinking, executing)
- **Sidebar:** Active Goals, Knowledge (memories)
- **Editor Tab:** Goal detail view — objective, plan checklist, activity feed

## UI / UX

### Sidebar

| Panel | Content |
|-------|---------|
| **Sessions** | Active + recent chat sessions (primary, top) |
| **Goals** | Active + recent goals with status badges (secondary) |
| **Context** | Searchable memory browser (pgvector hybrid retrieval) |

### Editor Tab (Goal View)

Opens when a goal is selected. Contains:

- **Top:** Objective text, status badge, progress bar
- **Center scrolled:** Task checklist (plan), activity feed (recent actions)
- **Bottom:** Goal actions (start, pause, resume, archive)

### State Indicator (Mascot)

The legacy dog sprite sheet (6.3MB, 8-frame PNG) is **deprecated**. Replaced by an inline SVG geometric indicator:

```
<svg viewBox="0 0 16 16">
  <circle class="ring" cx="8" cy="8" r="7"/>     <!-- concentric ring -->
  <circle class="core" cx="8" cy="8" r="4"/>     <!-- central core -->
</svg>
```

States driven by CSS keyframes mapped to `BridgeAgentState`:
- **Idle:** ring pulses (breathe)
- **Thinking:** core expands/contracts
- **Executing:** core spins
- **Success:** core pops up
- **Error:** core shakes

20KB total — no external assets, no canvas, no rAF loops.

### Memory System

pgvector hybrid retrieval now **prioritizes goal-relevant context**:

| Weight | Term | Purpose |
|--------|------|---------|
| 0.25 | Vector similarity | Semantic match |
| 0.20 | BM25 keyword | Exact terminology |
| 0.15 | Recency | Recent over old |
| 0.15 | Importance | High-value memories |
| 0.20 | Workspace/goal boost | Local context preference |
| 0.05 | Access frequency | Frequently used |

**What's stored:** Architectural decisions, completed tasks, bug fixes, user preferences.

**What's NOT stored:** Transient debug state, small talk, raw tool output.

## Local LLM Support

Default: **Ollama + phi4-mini** (2.5GB, no API key required).

Fallback: llama3.2 if primary model fails.

Cloud models: DeepSeek, OpenAI, Anthropic, OpenRouter — dropdown selector with API key gate.

## Session Model

- Sessions track conversation history per workspace
- Sessions can be linked to Goals via `conversations.goal_id`
- Forking supported: `/fork` creates a child conversation branch
- Persisted in `workspaceState` across VS Code restarts

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11+ / TypeScript 5.x |
| LLM Provider | LiteLLM (cloud) + Ollama (local) |
| Database | PostgreSQL 16 + pgvector |
| Embeddings | Ollama + nomic-embed-text (768-dim) |
| DB Driver | asyncpg |
| Bridge Protocol | JSON-RPC 2.0 over subprocess stdin/stdout |
| Config | TOML (~/.memorydog/) |
| Testing | pytest + pytest-asyncio |
| Linting | ruff |
