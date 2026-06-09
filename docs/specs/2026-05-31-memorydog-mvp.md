# MemoryDog — Design Specification

**Date:** 2026-06-09
**Status:** Core Pipeline Complete — VS Code Extension Focus
**Target:** VS Code extension MVP

## Overview

MemoryDog is a memory-augmented coding agent that gets better the longer you work with it. Unlike stateless coding agents, it remembers previous conversations, design decisions, bugs, and project history across sessions.

The mascot is a dog because the agent "fetches" memories.

**MVP scope:** A shared `memorydog-core` Python library (persistent memory, hybrid retrieval, instincts, tool execution, multi-provider LLM) with two frontends:
- `memorydog-cli`: Textual TUI for development and debugging
- `memorydog-vscode`: VS Code extension with sidebar panels (chat, memory browser, instinct viewer, animated mascot)

The core value proposition — cross-session persistent memory — is verified and working. Current focus is packaging the VS Code extension as the primary user-facing product.

### Core Differentiators

1. **Persistent memory** — facts survive across sessions, not just within a context window
2. **Hybrid retrieval** — vector similarity + keyword search + recency + importance
3. **Instincts** — user-defined reusable procedural modules that guide agent behavior
4. **Dual frontend** — VS Code extension + Textual CLI sharing a single core library
5. **Dog persona** — animated mascot in VS Code sidebar, professional UX in chrome

---

## Architecture

### Architecture: Shared Core + Thin Frontends (Zero Duplication)

```
┌─────────────────────────────────────────────────┐
│ memorydog-core (Python package, zero UI)        │
│ ┌─────────────────────────────────────────────┐ │
│ │ Agent Loop  │ Memory CRUD │ Retrieval       │ │
│ │ Tools (x7)  │ Ranking     │ Instinct Engine │ │
│ │ Provider    │ Context     │ DB Layer        │ │
│ └─────────────────────────────────────────────┘ │
└──────────┬──────────────────┬───────────────────┘
           │ imports          │ subprocess bridge
           ▼                  ▼
┌──────────────────────┐  ┌────────────────────────────┐
│ memorydog-cli        │  │ memorydog-vscode            │
│ Textual TUI frontend │  │ TypeScript extension        │
│ • Multi-pane layout  │  │ • Bridge: Python subprocess │
│ • Conversation view  │  │ • Chat webview with stream │
│ • File preview       │  │ • Memory browser panel     │
│ • Tool output        │  │ • Instinct viewer panel    │
│ • 🐕 Status bar      │  │ • Animated dog mascot      │
└──────────────────────┘  │ • Status bar integration  │
                          └────────────────────────────┘
           │
           │ asyncpg
           ▼
┌─────────────────────────────────────────────────┐
│ PostgreSQL 16 + pgvector (local, Docker)        │
│ 5 tables, HNSW index, full-text search          │
└─────────────────────────────────────────────────┘
```

**Zero duplication.** One implementation of memory, retrieval, instincts, and agent behavior — shared by both frontends.

**Why core+frontends split?** The agent logic is a reusable Python package. The CLI and VS Code extension are thin importers. This keeps all business logic in one place, prevents duplication, and lets the VS Code extension deliver a richer UX (animated dog, memory browser) without touching the core agent code.

**Why no server?** The agent IS the product. A REST API adds 50% more code for zero interview value. PostgreSQL is fast enough for single-user workloads. If you ever need multi-user, the memory layer is already cleanly separated in `db.py` and `memory.py` — wrapping it in FastAPI later is straightforward.

**Why no Redis?** HNSW indexes make vector search sub-millisecond. PostgreSQL full-text search is fast. A single user doesn't saturate a local database. Add Redis only if you measure a real bottleneck (you won't at this scale).

**Why no background workers?** Embedding generation takes ~100ms via API — do it inline at memory creation time. The user is waiting for the agent's response anyway. No queue infrastructure needed.

---

## Database Schema — 5 Tables

```sql
-- Core memory storage
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    summary VARCHAR(512),
    embedding VECTOR(1536),
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'conversation', 'design_decision', 'learned_fact',
        'user_preference', 'task_history', 'code_snippet', 'bug'
    )),
    workspace_name TEXT NOT NULL,
    importance FLOAT DEFAULT 0.5,
    access_count INT DEFAULT 0,
    last_accessed TIMESTAMP DEFAULT NOW(),
    decay_factor FLOAT DEFAULT 1.0,
    tags TEXT[] DEFAULT '{}',
    source_turn_id UUID,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_memories_embedding ON memories
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_memories_fts ON memories
    USING gin (to_tsvector('english', content));
CREATE INDEX idx_memories_workspace ON memories (workspace_name);
CREATE INDEX idx_memories_tags ON memories USING gin (tags);

-- Conversation sessions
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_name TEXT NOT NULL,
    title VARCHAR(256),
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP
);

-- Individual messages in a conversation
CREATE TABLE conversation_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    tool_calls JSONB,
    token_count INT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Instinct activation log (instincts defined in TOML file)
CREATE TABLE instinct_activations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instinct_name TEXT NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    trigger_match_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Persistent user preferences
CREATE TABLE user_preferences (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**5 tables, not 17.** No users, no workspaces (just a `workspace_name` column), no memory chunks (memories are atomic), no memory relations, no memory tags (tags are a `TEXT[]` column), no instinct tables (instincts are TOML files), no retrieval events (access_count on memories suffices).

### Workspace Awareness

`workspace_name` is derived from the current directory name or git repo name. It scopes memory retrieval with a ranking boost — not a hard filter:

- Same workspace: **2.0x** score multiplier
- Different workspace: **1.0x** score multiplier
- Cross-workspace retrieval works but prefers local context

No workspace table, no management UI, no ownership model. Just a string field.

---

## Memory System

### Memory Types

| Type | Description |
|------|-------------|
| `conversation` | Things discussed |
| `design_decision` | Architectural choices made |
| `learned_fact` | Deduced information |
| `user_preference` | User's stated preferences |
| `task_history` | Completed tasks |
| `code_snippet` | Important patterns |
| `bug` | Bugs found and fixes applied |

### Importance Scoring

After extraction, each memory gets an initial importance (0.0–1.0) assessed by the extraction LLM. Importance updates over time:

- **On access:** +0.01 per retrieval (capped at 0.95)
- **On explicit save:** set to 0.90
- **Decay:** importance decays exponentially if memory is never accessed. Decay tracked via `decay_factor`: `decay_factor *= e^(-0.01 * days_since_last_access)`. Effective importance = `importance * decay_factor`.

### Memory Extraction

After each conversation turn where code was modified or 3+ tools were called:

1. Send conversation summary to LLM with extraction prompt
2. LLM returns JSON array of `{type, content, summary, importance, tags}`
3. For each extracted fact:
   - Check dedup: cosine similarity against existing memories > 0.95 → skip
   - Generate embedding via OpenAI API
   - Insert into `memories`
4. Rate limit: max 20 new memories per turn

### Memory Lifecycle (Simplified)

- **Store gate:** Importance must be > 0.2 to persist
- **Dedup:** Cosine similarity > 0.95 → skip on insert
- **Pruning:** Soft-delete memories with effective importance < 0.1 and no access in 180 days (simple SQL query, maybe run manually or via a basic cron comment in README)

Full consolidation, archival, and contradiction detection are deferred to post-MVP.

---

## Retrieval Pipeline

### Hybrid Ranking Formula (Current)

```
Score(m, q) = 0.25·V + 0.20·B + 0.15·R + 0.15·I + 0.20·W + 0.05·F
```

| Term | Definition |
|------|-----------|
| **V** Vector similarity | `(cos(emb_m, emb_q) + 1) / 2`  (pgvector cosine distance) |
| **B** BM25 relevance | `ts_rank(to_tsvector(content), plainto_tsquery(q))`  (PostgreSQL FTS) |
| **R** Recency | `e^(-0.01 * days_since_last_access)` |
| **I** Importance | `importance * decay_factor` |
| **W** Workspace boost | same workspace → 1.5, different → 1.0 |
| **F** Access frequency | logistic sigmoid of `access_count / mean_access_count` |

### Multi-Stage Retrieval

1. **Initial retrieval:** On every user turn, retrieve top-5 memories for prompt injection
2. **Triggered retrieval:** When agent reads a new file, encounters unfamiliar terms, or discovers new subsystems → additional retrieval (max 3 per turn)
3. **Explicit retrieval:** Agent can call `memory_search` tool directly

### Retrieval Query

```sql
WITH vector_results AS (
    SELECT id, content, summary, memory_type, workspace_name,
           importance, decay_factor, access_count, last_accessed,
           1 - (embedding <=> $query_embedding) AS vector_score
    FROM memories
    ORDER BY embedding <=> $query_embedding
    LIMIT 50
),
fts_results AS (
    SELECT id, content, summary, memory_type, workspace_name,
           importance, decay_factor, access_count, last_accessed,
           ts_rank(to_tsvector('english', content),
                   plainto_tsquery('english', $query_text)) AS bm25_score
    FROM memories
    WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $query_text)
    LIMIT 50
),
combined AS (
    SELECT * FROM vector_results
    UNION
    SELECT * FROM fts_results
)
SELECT id, content, summary, memory_type, workspace_name,
       vector_score, bm25_score,
       (0.25 * COALESCE(vector_score, 0) +
        0.20 * COALESCE(bm25_score, 0) +
        0.15 * EXP(-0.01 * EXTRACT(DAY FROM NOW() - last_accessed)) +
        0.15 * (importance * decay_factor) +
        0.20 * CASE WHEN workspace_name = $current_workspace THEN 2.0 ELSE 1.0 END +
        0.05 * (1.0 / (1.0 + EXP(-(access_count - $mean_access) / $mean_access)))
       ) AS final_score
FROM combined
ORDER BY final_score DESC
LIMIT 5;
```

### Cross-Encoder Reranking (Planned)

The current retrieval pipeline uses a **first-stage only** approach: hybrid vector + FTS search produces candidates, which are scored by the hand-tuned formula, and the top-5 are returned. This is fast and cheap but limited by the quality of the static ranking weights.

**Planned addition:** A second-stage cross-encoder reranker that improves precision at the cost of a small latency increase.

```
Query →
  Stage 1 (fast recall)
    ├── pgvector HNSW cosine search → top 50
    └── PostgreSQL FTS (GIN) → top 50
        → UNION → dedup → formula score → top 20
  Stage 2 (precision)
    └── Cross-encoder reranker
        → score each (query, candidate) pair
        → rerank by relevance → top 5
        → inject into prompt
```

**Why a cross-encoder?** Bi-encoder embeddings (like nomic-embed-text) compress a document into a single vector, losing nuance. A cross-encoder processes the query and candidate together, computing a joint relevance score. This is strictly more accurate for ranking than cosine similarity.

**Architecture:**

```python
# Pseudocode for the reranking stage
async def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    pairs = [(query, c["content"]) for c in candidates]
    scores = await cross_encoder.score(pairs)
    scored = list(zip(scores, candidates))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
```

**Candidate implementations:**

| Model | Size | Latency | Quality |
|-------|------|---------|---------|
| BAAI/bge-reranker-v2-m3 | ~2.2GB | ~50ms/pair | High (top on MTEB) |
| BAAI/bge-reranker-v2-minicpm-1b | ~1.1GB | ~30ms/pair | Good |
| ms-marco-MiniLM-L-6-v2 | ~80MB | ~10ms/pair | Adequate (lightweight) |

All can run locally via HuggingFace transformers or ONNX. No GPU required for batch sizes of 1-5 pairs.

**Integration:** The reranker is an additive stage. The first-stage hybrid search (HNSW + FTS → formula → top 20) remains unchanged. The cross-encoder reranks only the top 20, adding ~200ms-1s of latency depending on model size. If the reranker is unavailable or too slow, the system falls back to the formula-scored top-5.

**Evaluation:** Offline A/B comparison using the benchmark suite. Metric: NDCG@5 comparing formula-only vs formula + reranker rankings against human-judged relevance.

### Deferred (Post-MVP)

- Cross-encoder reranking
- Learning-to-rank (train weights from user interaction data)
- Memory selection models (classify "should this be stored?")
- Automatic instinct generation from behavioral patterns

### Design

Instincts are user-defined procedural modules stored in `~/.memorydog/instincts.toml`. They activate based on keyword triggers and influence both retrieval and agent behavior.

**No automatic discovery in MVP.** Pattern detection from behavioral data is deferred. The concept is demonstrated through manual instincts. "Future work: automatic instinct discovery" is an excellent interview answer.

### Format

```toml
[[instincts]]
name = "AI Evaluation Expert"
description = "Prioritizes benchmarks, metrics, and ablation studies"
triggers = ["benchmark", "evaluation", "metric", "ablation"]
prompt = """
When working on evaluation-related tasks:
- Consider benchmarks, metrics, and ablation studies
- Prioritize reproducibility and standard evaluation protocols
- Suggest statistical significance testing where applicable
"""
retrieval_bias = ["benchmark", "evaluation", "metric", "ablation", "accuracy", "precision", "recall"]

[[instincts]]
name = "Bug Hunter"
triggers = ["bug", "race condition", "deadlock", "fix", "debug", "crash"]
prompt = """
When fixing bugs:
- Add a regression test before fixing
- Check for similar issues in related code paths
- Consider edge cases and concurrency
"""
retrieval_bias = ["bug", "fix", "debug", "test", "regression", "concurrency"]

[[instincts]]
name = "NeuralGomoku Expert"
triggers = ["neuralgomoku", "mcts", "self-play", "gomoku"]
prompt = """
When working on NeuralGomoku:
- Inspect MCTS implementation, self-play pipeline, training loop, model architecture
- Check evaluation metrics before proposing changes
"""
retrieval_bias = ["mcts", "self-play", "training", "model", "evaluation", "gomoku"]
```

### Activation

At the start of each agent turn:

1. Match user query + workspace name against all instinct triggers
2. Activate instincts with ≥ 1 matching trigger, max 3 active
3. Active instincts produce two effects:
   - **Retrieval bias:** Augment retrieval query with `retrieval_bias` terms
   - **Prompt injection:** Insert `prompt` text into system prompt (wrapped in `[ACTIVE INSTINCT: name]` block)
4. Log activation to `instinct_activations` table

---

## VS Code Extension

### Architecture: Subprocess Bridge

MemoryDog's VS Code extension communicates with the Python core via a `MemoryDogBridge` — a subprocess manager that spawns `memorydog-core` as a child process and communicates over stdin/stdout JSON-RPC.

```
VS Code Extension (TypeScript)
  │
  ├── ChatViewProvider       — sidebar webview, streaming tokens
  ├── MemoryPanelProvider    — browse/search memories
  ├── InstinctPanelProvider  — view loaded instincts
  ├── DogViewProvider        — animated mascot (CSS states)
  ├── StatusBar              — memory count, instinct count, workspace
  └── MemoryDogBridge        — stdin/stdout JSON-RPC to Python
        │
        ▼
Python subprocess (memorydog-core)
  │
  ├── agent_loop.run_turn()  — full agent pipeline
  ├── memory.*               — CRUD, extraction, embedding
  ├── retrieval.*            — hybrid search, ranking
  └── instincts.*            — TOML loading, matching
```

### Bridge Protocol

The bridge uses JSON-RPC over stdin/stdout. Each request is a JSON line:

```json
{"id": 1, "method": "chat", "params": {"text": "Hello", "workspace": "my-project"}}
```

The Python process writes JSON response lines:

```json
{"id": 1, "result": {"content": "Hello! How can I help?"}}
```

For streaming, status messages are sent as separate JSON lines:

```json
{"type": "status", "text": "Fetching memories..."}
{"type": "token", "text": "Based"}
{"type": "token", "text": " on"}
```

### Extension Capabilities

| Feature | Implementation |
|---------|---------------|
| **Chat** | Webview with message history, input box, streaming token display. Bridge handles `run_turn()` pipeline — status messages update UI in real time, tokens stream as they arrive. |
| **Memory browser** | Webview listing memories with workspace filter, search, type badges, importance indicators. Data fetched via bridge `getMemories()` which calls `retrieve_memories()` in core. |
| **Instinct viewer** | Webview showing loaded instincts, trigger keywords, activation status. Data from bridge `getInstincts()` which reads `~/.memorydog/instincts.toml`. |
| **Dog mascot** | CSS-animated dog with 4 states: idle (resting), sniffing (searching), excited (found something), sleeping (bridge down). States driven by status message keywords from the bridge. |
| **Status bar** | Shows `🐕 N memories | M instincts` updated every 30s via bridge `getStatus()`. |

### Packaging

The extension is packaged with `vsce package`:
```bash
cd vscode
npx @vscode/vsce package
# → memorydog-0.1.0.vsix (12KB, 10 files)
```

### Configuration

Users set their API key via:
1. The extension's config command (stored in VS Code settings under `memorydog.*`)
2. The chat panel's setup screen
3. Directly via VS Code settings UI

The bridge syncs the key to `~/.memorydog/config.toml` on startup.

---

## Agent Behavior

### Execution Loop

```
1. 🐕 Load instincts (TOML), match triggers, activate
2. 🐕 Fetch memories (hybrid retrieval, biased by active instincts)
3. Construct system prompt (base + memories + instinct prompts + tools + workspace)
4. LLM call via LiteLLM (streaming to TUI)
5. If plan block emitted → render Rich panel, continue
6. If tool call → execute locally → back to step 4 with tool results
7. If final response → extract memories from turn → store to DB
8. Display response, update status bar
```

### Plan Visibility

When the agent begins a multi-step task, it emits a JSON plan block. The CLI parses it and renders a Rich panel. Detailed reasoning is internal — never emitted.

```
🐕 Plan:
  1. Inspect relevant files
  2. Understand current implementation
  3. Apply changes
  4. Run tests
  5. Verify results
```

### Dog Persona Integration

The persona appears in **chrome only** — never in agent responses to the user:

| Trigger | Message |
|---------|---------|
| Memory retrieval start | 🐕 Fetching memories... |
| Memories found | 🐕 Found N related memories |
| Workspace recognized | 🐕 I remember this project. N past conversations. |
| High-value memory created | 🐕 Learned a new trick |
| Instinct activated | 🐕 Instinct activated: [name] |
| Memory stored | 🐕 Remembered that. |
| Status bar (always) | 🐕 Ready. N memories. M instincts. workspace: [name] |

### Memory Store / Ignore Policy

**Store when:** Design decisions made, bugs identified/fixed, user preferences stated, non-trivial implementation details, explicit "remember" command.

**Ignore when:** Small talk, greetings, transient debug state (current variable values), duplicate facts, tool output that's not semantically meaningful.

---

## Roadmap — Current State

### ✅ Complete: Core Pipeline (Weeks 1-3)

**Persistent memory, hybrid retrieval, instincts, tool system, embeddings, cross-session recall.**

- LiteLLM multi-provider integration (DeepSeek, OpenAI, etc.)
- Textual TUI with multi-pane layout, streaming, status bar
- 7 tools: read, write, edit, bash, glob, grep, memory_search
- PostgreSQL 16 + pgvector: 5 tables, HNSW index, FTS GIN index
- Hybrid retrieval: vector cosine + BM25 + recency + importance + workspace boost + access frequency
- Automatic memory extraction from conversation turns
- Cross-session recall: memories persist across `dog chat` sessions
- Instinct engine: TOML-defined modules with keyword triggers, retrieval bias, prompt injection
- Memory extraction defense: 12 failure modes handled (prose, fences, unquoted keys, etc.)
- Ranking: sanitized formula with edge-case handling
- Multi-stage retrieval: initial + triggered + retrieval budget (max 3 triggered, max 10 total)
- 104 tests, ruff clean, all diagnostics green

### ✅ Complete: VS Code Extension (Week 5-6)

**Full VS Code extension with 4 sidebar panels, bridge, streaming.**

- MemoryDogBridge: Python subprocess manager with stdin/stdout JSON-RPC
- Chat panel: webview with message history, streaming token display, status updates
- Memory browser panel: searchable list with workspace filter
- Instinct viewer panel: status badges, descriptions
- Animated dog mascot: CSS-driven idle/sniffing/excited/sleeping states
- Status bar: real-time memory count, instinct count, workspace name
- Configuration: API key management via VS Code settings
- Packaged as `.vsix` (12KB, 10 files)

### In Progress

- Windows bridge support (named pipes vs Unix signals)
- Extension marketplace publishing
- Demo video: cross-session memory recall in VS Code

### Post-MVP (Deferred)

- Memory consolidation (summarization of old memories)
- Confidence scoring for retrieval
- Behavioral pattern detection → automatic instinct generation
- Cross-encoder reranking for precision improvement
- Benchmarks (4-task A/B suite, memory ON vs OFF)

---

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Language (Core) | Python 3.11+ | Dominant in AI/ML, rich ecosystem |
| Language (Extension) | TypeScript 5.x | VS Code API native |
| CLI Framework | Textual + Rich | Multi-pane TUI, professional look |
| LLM Provider | LiteLLM | 100+ providers, one interface |
| Database | PostgreSQL 16 + pgvector | Vector + relational in one DB, FTS built in |
| Embeddings | Ollama + nomic-embed-text | Local, private, 768-dim |
| DB Driver | asyncpg | Async PostgreSQL driver |
| Extension Bridge | JSON-RPC over subprocess stdin/stdout | Zero dependency, no server |
| Config | TOML (tomllib) | Python stdlib, human-readable |
| Testing | pytest + pytest-asyncio | Industry standard |
| Linting | ruff | Fast, all-in-one |

### Dependencies

```
Core: litellm, asyncpg, pgvector, httpx, pydantic
CLI: textual, rich
VS Code: @types/vscode, typescript
Dev: pytest, pytest-asyncio, ruff
```

---

## Folder Structure

```
memorydog/              # monorepo
├── core/               # memorydog-core — shared Python package, zero UI
│   ├── agent_loop.py   # Execution loop, streaming, callbacks
│   ├── tools.py        # 7 tools + memory_search
│   ├── provider.py     # LiteLLM provider, streaming, error handling
│   ├── memory.py       # CRUD, extraction, embedding, parsing
│   ├── retrieval.py    # Hybrid search, budgeting, triggered retrieval
│   ├── ranking.py      # Scoring formula, sanitize
│   ├── instincts.py    # TOML loading, matching, bias
│   ├── db.py           # asyncpg pool, migrations
│   ├── config.py       # TOML config, env var fallback
│   └── context.py      # Prompt construction
├── cli/                # memorydog-cli — Textual TUI frontend
│   ├── main.py         # Entry point (dog chat/config/status)
│   ├── app.py          # Textual App + CSS
│   └── ui/
│       ├── chat.py     # Chat screen, status messages, streaming
│       └── widgets.py  # StatusBar, PlanPanel, DiffPreview, ToolOutput
├── vscode/             # memorydog-vscode — TypeScript extension
│   ├── package.json    # 9 activation events, 4 webview panels
│   ├── tsconfig.json
│   ├── src/
│   │   ├── extension.ts    # Activation, 4 providers, bridge
│   │   ├── bridge.ts       # Python subprocess JSON-RPC
│   │   └── webview/
│   │       ├── chat.html       # Chat panel with streaming
│   │       ├── chat.js
│   │       ├── memory.html     # Memory browser
│   │       ├── instinct.html   # Instinct viewer
│   │       └── dog.html        # Animated mascot
│   └── assets/dog/         # Dog sprite assets
├── migrations/
│   └── 001_init.sql        # 5 tables, HNSW, FTS
├── tests/
│   ├── test_tui.py          # 38 tests (provider, config, ranking, instincts)
│   ├── test_extraction.py   # 42 tests (parsing, validation)
│   ├── test_retrieval.py    # 24 tests (budget, triggers, logging)
│   ├── test_integration.py  # 6 tests (full pipeline)
│   └── benchmarks/          # A/B comparison harness
├── docker-compose.yml       # pgvector/pgvector:pg16
├── dog                      # Launcher script (auto-activates venv)
└── pyproject.toml

---

## Benchmarking (Deferred)

If time permits, a 4-task A/B comparison (memory ON vs OFF) measuring task success, context retention, preference adherence, and completion time. Not required for the MVP demo — the agent remembering across sessions is itself the proof.

---

## Resume Description

**MemoryDog** — *Python, PostgreSQL/pgvector, LiteLLM, TypeScript, VS Code API*

Designed and built a memory-augmented coding agent with persistent long-term memory across sessions and projects. Implemented a hybrid retrieval pipeline combining vector similarity (pgvector HNSW), BM25 keyword search, recency weighting, and importance scoring with configurable ranking formulas. Built an automatic memory extraction system that identifies and stores design decisions, bugs, and user preferences from conversations. Designed an instinct system that activates user-defined procedural modules to bias retrieval and guide agent behavior based on task context. Developed both a multi-pane Textual-based CLI TUI and a VS Code extension with sidebar webviews (chat with streaming, memory browser, instinct viewer, animated mascot) — both frontends share a single `memorydog-core` Python library with zero logic duplication via a subprocess JSON-RPC bridge.
