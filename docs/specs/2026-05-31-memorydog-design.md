# MemoryDog — Design Specification

**Date:** 2026-05-31
**Status:** Design Complete

## Overview

MemoryDog is a memory-augmented coding agent whose primary differentiator is persistent long-term memory across sessions, workspaces, and projects. Unlike stateless coding agents constrained by context windows, MemoryDog remembers previous conversations, design decisions, bugs, implementation details, and project history over weeks or months.

The mascot is a dog because the agent "fetches" memories.

### Core Philosophy

| Pillar | Meaning |
|--------|---------|
| **Memory** | Remembers facts, conversations, design decisions, project context, user preferences, and task history — indefinitely. |
| **Instincts** | Learns reusable procedural modules from repeated behavior patterns. Automatically discovered and refined. |
| **Agent** | Adapts — gets better the longer you work with it through accumulation of both memories and instincts. |

MemoryDog is a **developer-first coding agent**, not a general-purpose chat assistant. The UX is optimized for reading code, editing code, viewing diffs, running commands, understanding repository context, and long-running coding sessions.

### Deployment Model

Multi-user, multi-tenant capable. CLI runs locally on user's machine. FastAPI server provides memory/instincts as a service. Designed for single-user use but architected for multi-tenancy from day one.

---

## 1. System Architecture

### High-Level Topology

```
User's Machine                          Cloud / Self-Hosted                External
┌─────────────────────────┐           ┌──────────────────────┐           ┌─────────────┐
│ CLI Client (Textual TUI)│  HTTPS   │ MemoryDog Server     │           │ LiteLLM     │
│ ┌─────────────────────┐ │ ───────→ │ ┌──────────────────┐ │           │ • OpenAI    │
│ │ Agent Loop          │ │ ←─────── │ │ FastAPI REST API  │ │           │ • Anthropic │
│ │ • Context Builder   │ │  REST    │ │ /memories         │ │           │ • Gemini    │
│ │ • LLM Call (LiteLLM)│ │          │ │ /retrieve         │ │           │ • DeepSeek  │
│ │ • Tool Router       │ │          │ │ /instincts        │ │           │ • OpenRouter│
│ │ • Response Parser   │ │          │ │ /workspaces       │ │           │ • Ollama    │
│ ├─────────────────────┤ │          │ │ /users            │ │           └─────────────┘
│ │ Local Tools         │ │          │ └──────────────────┘ │
│ │ read/write/edit     │ │          │ ┌──────────────────┐ │           ┌─────────────┐
│ │ bash/glob/grep      │ │          │ │ PostgreSQL+pgvector│           │ Embedding   │
│ │ memory_search       │ │          │ │ • Users/Workspaces │           │ API         │
│ └─────────────────────┘ │          │ │ • Memories/Vectors │           │ • OpenAI    │
│ ┌─────────────────────┐ │          │ │ • Instincts        │           │ • Cohere    │
│ │ TUI (Textual+Rich)  │ │          │ └──────────────────┘ │           └─────────────┘
│ │ • Conversation pane │ │          │ ┌──────────────────┐ │
│ │ • File preview      │ │          │ │ Redis            │ │
│ │ • Diff viewer       │ │          │ │ • Session cache   │ │
│ │ • Tool output       │ │          │ │ • Retrieval cache │ │
│ │ • 🐕 Status bar     │ │          │ │ • Embedding cache │ │
│ └─────────────────────┘ │          │ └──────────────────┘ │
└─────────────────────────┘          │ ┌──────────────────┐ │
                                     │ │ Workers (taskiq)  │ │
                                     │ │ • Embedding gen   │ │
                                     │ │ • Consolidation   │ │
                                     │ │ • Pattern detect  │ │
                                     │ │ • Memory decay    │ │
                                     │ └──────────────────┘ │
                                     └──────────────────────┘
```

### Key Design Decisions

**Why Textual over Rich for the TUI?** Rich gives beautiful output. Textual gives an interactive application with multiple live-updating panes, keyboard navigation, and reactive state. For a coding agent where users watch file previews, diffs, and tool output in real time alongside conversation, Textual is the only framework supporting true multi-pane layouts. Rich is used internally for formatting (panels, syntax highlighting, markdown).

**Why FastAPI over Django/Flask?** Async-native endpoints with automatic OpenAPI docs, Pydantic validation, and dependency injection. For an API doing database lookups and async embedding calls, async is the right model.

**Why LiteLLM as the provider layer?** Normalizes 100+ LLM providers into a single OpenAI-compatible interface. MemoryDog writes zero provider-specific code. Switching providers is a config change.

**Why not use an agent framework (LangChain, etc.)?** Building from scratch gives full control over the agent loop, memory injection, and tool execution. Maximum learning value and portfolio signal. No framework abstractions to fight.

**Why client-server split (not monolithic)?** The CLI handles everything the user interacts with (agent loop, tools, UI). The server is purely a memory/instincts backend. This is how production systems (GitHub Copilot, Cursor) work — local agent process + cloud intelligence. Multi-tenant from day one.

### TUI Layout

| Conversation Pane (2/4) | File Preview (1/4) | Tool Output (1/4) |
|--------------------------|-------------------|-------------------|

Bottom status bar: `🐕 Ready. 1,247 memories. 3 instincts. | workspace: neural-gomoku | Session: 23m | Tokens: 14.2k | Model: claude-sonnet-4-20250514`

### Configuration

Stored at `~/.memorydog/config.toml`:

```toml
[provider]
api_base = "https://api.anthropic.com"
api_key = "sk-..."
model = "claude-sonnet-4-20250514"

[server]
url = "https://memorydog.example.com"
api_key = "md-..."

[embedding]
provider = "openai"
model = "text-embedding-3-small"
```

---

## 2. Memory Architecture

### Database Schema

12 tables, PostgreSQL 16 + pgvector extension.

| Table | Purpose |
|-------|---------|
| `users` | User accounts with API key hashes |
| `workspaces` | Project directories linked to users |
| `memories` | **Core table** — facts with vector embeddings (1536d) |
| `memory_chunks` | Chunked long content (>512 tokens) |
| `memory_tags` | Categorization tags |
| `memory_relations` | Relationships between memories (references, contradicts, extends, supersedes, summarizes) |
| `conversations` | Session records |
| `conversation_turns` | Individual messages with tool calls |
| `user_preferences` | Key-value settings |
| `retrieval_events` | Audit log for retrieval analytics |
| (Instinct tables — see Section 4) | |

### `memories` Core Table

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users NOT NULL,
    workspace_id UUID REFERENCES workspaces NOT NULL,
    memory_type TEXT NOT NULL,  -- conversation, workspace, project, user_preference,
                                -- design_decision, learned_fact, task_history, code_snippet
    content TEXT NOT NULL,
    summary VARCHAR(512),
    embedding VECTOR(1536),
    importance FLOAT DEFAULT 0.5,
    confidence FLOAT DEFAULT 0.7,
    access_count INT DEFAULT 0,
    last_accessed TIMESTAMP,
    decay_factor FLOAT DEFAULT 1.0,
    is_consolidated BOOL DEFAULT FALSE,
    is_archived BOOL DEFAULT FALSE,
    parent_memory_id UUID REFERENCES memories,
    source_conversation_id UUID REFERENCES conversations,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_memories_fts ON memories USING gin (to_tsvector('english', content));
```

### Memory Types

| Type | Description |
|------|-------------|
| `conversation` | Things discussed in conversations |
| `workspace` | Facts about the project/codebase structure |
| `project` | Design decisions, architecture notes |
| `user_preference` | User's preferences and habits |
| `design_decision` | Architectural choices made |
| `learned_fact` | Things the agent deduced |
| `task_history` | Previously completed tasks |
| `code_snippet` | Important code patterns |

### Memory Lifecycle

```
Capture → Rank → Consolidate → Archive → Retire
```

1. **Capture:** Raw facts extracted from conversations by LLM. Deduped on insert (cosine > 0.95 → merge). Minimum importance gate (0.2).
2. **Rank:** Importance + confidence scored. Relations established. Tags assigned.
3. **Consolidate:** Group similar memories → summarize via LLM. Nightly cron job. Original memories persist with reduced weight.
4. **Archive:** Low importance + old → excluded from default retrieval. Still retrievable if explicitly searched.
5. **Retire:** Superseded by consolidated memory. Soft-deleted.

### Importance Scoring

```
importance = 0.30 × explicit_marking + 0.25 × access_frequency + 0.20 × recency_of_access + 0.15 × llm_assessed + 0.10 × relation_count
```

### Confidence Scoring

Orthogonal to importance. Measures how certain we are the memory is correct.

| Source | Initial Confidence |
|--------|-------------------|
| User explicit statement | 0.95 |
| Tool output fact | 0.90 |
| Consolidation output | 0.80 |
| LLM extraction | 0.70 |
| Reflection summary | 0.65 |
| Corroborated by ≥2 sources | +0.15 |
| Contradicted by another memory | -0.30 |
| Aged > 90 days without access | -0.05/month |

### Memory Pollution Prevention

- **Storage gate:** Memory must exceed minimum importance (0.2) to be stored
- **Dedup check:** Before INSERT, cosine similarity check. If > 0.95, merge.
- **Pruning:** Max 10,000 memories per workspace. Evict lowest (importance × confidence).
- **Decay:** `decay = e^(-λ × days_since_creation)` with λ = 0.01 (half-life ~69 days). Access resets decay.
- **Rate limiting:** Max 50 new memories per conversation turn.
- **Store vs Ignore:** Design decisions, bugs, preferences → store. Small talk, transient debug state, duplicates → ignore.

### Contradiction Handling

During consolidation, semantic contradictions are detected between memories. Resolution rules:
1. Newer memory wins by default
2. Confidence-aware: high-confidence old > low-confidence new
3. Explicit user statements overrule extracted facts
4. Contradiction recorded as `memory_relation` (type = "contradicts")

---

## 3. Retrieval Pipeline

### Multi-Stage Retrieval

Memory retrieval is **not a single pre-fetch**. It triggers at multiple points during the agent loop:

1. **Initial Retrieval** — Based on user query + workspace context
2. **Triggered Retrieval** — When agent encounters new files, subsystems, or unfamiliar terms
3. **Explicit Retrieval** — When agent calls the `memory_search` tool

**Budgets:** Max 3 additional retrievals per turn. Max 10 retrieved memories total per turn. Subsequent retrievals are cheaper (embedding cached).

### Hybrid Ranking Formula

```
Score(m, q) = 0.35·V(m,q) + 0.20·B(m,q) + 0.15·R(m) + 0.15·I(m) + 0.10·W(m) + 0.05·F(m)
```

| Term | Definition | Default Weight |
|------|-----------|----------------|
| **V(m,q)** Vector similarity | `(cos(emb_m, emb_q) + 1) / 2` | 0.35 |
| **B(m,q)** BM25 relevance | `ts_rank(normalized, 32)` | 0.20 |
| **R(m)** Recency | `e^(-λ · days_since_access)`, λ = 0.01 | 0.15 |
| **I(m)** Importance | `importance ∈ [0, 1]` | 0.15 |
| **W(m)** Workspace boost | same_ws → 1.5, related → 1.0, unrelated → 0.6 | 0.10 |
| **F(m)** Access frequency | `σ(access_count / μ)`, logistic sigmoid | 0.05 |

Candidates from vector search (top-50) and BM25 (top-50) are unioned, scored, and ranked. Optionally reranked with cross-encoder on top-20.

Workspace relatedness (for W(m) multiplier) is determined by: shared git remote origin, overlapping memory tags, or explicit user grouping. Default: same workspace → 1.5, different workspace → 1.0 unless relatedness is established.

### Redis Caching (4 layers)

| Layer | Content | TTL |
|-------|---------|-----|
| L1 | Session context cache (current conversation's injected memories) | Session duration |
| L2 | Workspace summary cache (top concepts, key files) | 1 hour |
| L3 | Retrieval result cache (query → results) | 5 minutes |
| L4 | Embedding cache (content hash → vector) | 30 days |

---

## 4. Agent Behavior

### Agent Execution Loop

```
1. 🐕 Memory & Instinct Pre-Fetch (GET /retrieve, GET /instincts/active)
2. Prompt Construction (base + memories + instincts + tools + workspace context)
3. LLM Call (LiteLLM, streaming response to TUI)
4. Parse & Route (text → display. tool_call → execute locally)
5. Loop Decision (more tools → back to step 3. final response → step 6)
6. 🐕 Memory Extraction & Storage (extract facts → POST /memories)
```

### Plan Visibility

When beginning a multi-step task, the agent emits a plan as a JSON block. The CLI parses it and renders a high-level plan panel. Detailed reasoning stays internal — never emitted to the user.

```
🐕 Plan:
  1. Inspect relevant files
  2. Understand current implementation
  3. Apply changes
  4. Run tests
  5. Verify results
```

### Conditional Reflection

Reflection does NOT run after every task. It is expensive and runs only when:
- Code was modified (write/edit called)
- 3+ tool calls occurred
- A significant task completed
- New memory has importance > 0.7
- User explicitly approves a solution

Reflection outputs: new memories, confidence updates, instinct pattern signals, optional proactive suggestion.

### Dog Persona Integration

The persona appears in **chrome only** — never in agent output to the user:

| Context | Message |
|---------|---------|
| Memory retrieval start | 🐕 Fetching memories... |
| Memory found | 🐕 Found X-related memory from N days ago |
| Workspace recognized | 🐕 I remember this project. [N] past conversations. |
| New knowledge captured | 🐕 Learned a new trick |
| Instinct created | 🐕 Promoted repeated workflow into an instinct |
| Consolidation ran | 🐕 Consolidating memories overnight... |
| Status bar | 🐕 Ready. [N] memories. [M] instincts. |

**Must NOT appear:** In any LLM-generated response to the user. The agent writes professional, direct output. The persona is chrome, not content.

---

## 5. Instincts Subsystem

### Instinct vs Memory

| | Memory | Instinct |
|---|--------|----------|
| **Nature** | Passive knowledge (what is true) | Active behavior (how to work) |
| **Example** | "User implemented MCTS using PUCT" | "When working on Go engines, inspect MCTS, self-play, training pipeline, and eval metrics before proposing changes" |
| **Role** | Retrieved when relevant. Injected as context. | Modifies agent's workflow, retrieval strategy, and system prompt. |

**Rule of thumb:** A memory says "X is true." An instinct says "when Y happens, do Z." Instincts are procedural.

### Database Schema

5 tables extend the core schema:

| Table | Purpose |
|-------|---------|
| `instincts` | Core instinct record: name, description, prompt_injection, retrieval_bias |
| `instinct_triggers` | Conditions that activate this instinct (keywords, workspace, tags) |
| `instinct_versions` | Version history with changelogs |
| `instinct_activations` | Activation log with feedback (was_useful) |
| `behavioral_patterns` | Raw signals before promotion — tool sequences, topic co-occurrence, task structures |

### Activation Pipeline

```
Query → Trigger Match → Rank Candidates → Activate (top-3, score > 0.4) → Apply Effects
```

**Ranking formula:**
```
activation_score = 0.4 × trigger_match + 0.3 × historical_usefulness + 0.2 × recency + 0.1 × usage_frequency
```

**Applied effects:**
1. **Bias retrieval** — Augmented query with instinct-specific bias terms (from `retrieval_bias` JSONB)
2. **Inject prompt** — Instinct instructions inserted into system prompt

**Safety:** Max 3 active simultaneously. Each prompt_injection limited to 200 tokens. Instincts are guidance, not rules — agent can deviate when inappropriate.

### Learning Pipeline

1. **Observe:** Background worker analyzes `behavioral_patterns` for recurring signals (tool sequences, topic co-occurrence, task structures)
2. **Evaluate:** Threshold check — ≥ 5 occurrences within 30 days, ≥ 70% pattern match rate
3. **Generate:** LLM synthesizes an instinct: name, description, prompt_injection, triggers, retrieval_bias
4. **Notify:** 🐕 Promoted repeated workflow into an instinct: [name]

### Lifecycle

| Operation | Mechanism |
|-----------|-----------|
| **Auto-create** | Pattern detector hits threshold → LLM generates instinct → status=active |
| **Manual create** | `dog instinct create <name>` with triggers and instructions |
| **Auto-refine** | If was_useful rate < 50%, LLM refines triggers/prompt. New version created. |
| **Manual edit** | `dog instinct edit <name>`. Opens editor. New version. |
| **Versioning** | Every change creates version row. `dog instinct history <name>`. |
| **Merging** | Overlapping triggers (>40% shared trigger values) + similar prompt_injection (cosine > 0.7 on embeddings) → suggest merge. `dog instinct merge a b`. |
| **Deletion** | Manual: `dog instinct delete`. Auto: if was_useful < 10% over 20 activations → deprecated → deleted after 60 days. |

### CLI Commands

```
dog instinct list
dog instinct show <name>
dog instinct create <name>
dog instinct edit <name>
dog instinct delete <name>
dog instinct pause <name>
dog instinct resume <name>
dog instinct history <name>
dog instinct merge <a> <b>
dog instinct feedback <name> (useful/not-useful)
```

---

## 6. MVP Roadmap

### Phase 1: Stateless Coding Agent (2-3 weeks)
**Deliverables:** Textual TUI with conversation pane, agent loop, LiteLLM provider integration, 6 tools (read/write/edit/bash/glob/grep), config file, streaming responses. No memory, no server, no DB.

**Folder:** `memorydog/cli/` (app.py, agent_loop.py, tools/, provider/, ui/)

**Resume value:** Medium — TUI design, tool execution, LLM integration.

### Phase 2: Memory Server + Basic Storage (3-4 weeks)
**Deliverables:** FastAPI server, PostgreSQL + pgvector, user/workspace CRUD, memory CRUD with vector search, MemoryClient in CLI, basic prompt injection, Docker Compose, API key auth.

**Folder:** `memorydog/server/` (api/, models/, db.py), `migrations/001_initial.sql`

**Resume value:** High — API design, database schema, distributed systems.

### Phase 3: Hybrid Retrieval + Ranking (3-4 weeks)
**Deliverables:** PostgreSQL FTS, hybrid ranking formula, 4-layer Redis caching, retrieval events tracking, memory confidence scoring, multi-stage retrieval triggers, retrieval budgets.

**Folder:** `server/services/` (retrieval.py, ranking.py, embedding.py), `migrations/002_fts_confidence.sql`

**Resume value:** Very High — IR systems, ranking algorithms, caching architecture.

### Phase 4: Automatic Memory Extraction (3-4 weeks)
**Deliverables:** LLM-based fact extraction, deduplication, importance scoring, auto-tagging, relation detection, storage gate, conversation persistence, dog persona chrome.

**Folder:** `server/services/` (extraction.py, dedup.py), `server/workers/extraction_worker.py`, `cli/prompts/system.py`

**Resume value:** Very High — LLM pipelines, NLP, extraction systems.

### Phase 5: Memory Lifecycle (3-4 weeks)
**Deliverables:** Nightly consolidation, memory summarization, decay scheduling, archival, contradiction handling, storage eviction, conditional reflection, plan visibility, workspace summaries.

**Folder:** `server/workers/` (consolidation.py, decay.py, reflection.py), `migrations/004_lifecycle.sql`

**Resume value:** Very High — data lifecycle management, background workers, summarization.

### Phase 6: Instincts (4-6 weeks)
**Deliverables:** Behavioral pattern detection, instinct CRUD API, LLM-based instinct generation, activation pipeline, retrieval bias, versioning + refinement, merging + deletion, CLI commands, safety guards.

**Folder:** `server/models/` (instinct.py, behavioral_pattern.py), `server/services/` (instinct_engine.py, pattern_detector.py, instinct_generator.py), `cli/commands/instinct.py`

**Resume value:** Extremely High — unsupervised pattern discovery, agent self-improvement.

### Phase 7: Benchmarks (1 week)
**Deliverables:** 4 benchmark tasks, single run.py script, A/B comparison (memory ON vs OFF), 5 metrics, simple comparison table output.

**Folder:** `tests/benchmarks/` (run.py, tasks.py, README.md)

**Resume value:** Very High — evaluation methodology, quantitative evidence.

### Summary

| Phase | Focus | Difficulty | Weeks |
|-------|-------|-----------|-------|
| 1 | Stateless Agent CLI | Medium | 2-3 |
| 2 | Memory Server + Storage | Med-Hard | 3-4 |
| 3 | Hybrid Retrieval + Ranking | Hard | 3-4 |
| 4 | Auto Memory Extraction | Hard | 3-4 |
| 5 | Memory Lifecycle | Hard | 3-4 |
| 6 | Instincts | Very Hard | 4-6 |
| 7 | Benchmarks | Med-Hard | 1 |

**MVP (Phases 1-3):** 8-11 weeks. **Full system:** ~6 months.

---

## 7. Benchmarking

### Philosophy

Build first, benchmark second. The evaluation exists only to demonstrate that memory provides value — not to publish a paper. Minimum viable evidence: credible, measurable, interview-ready results.

### Benchmark Suite — 4 Tasks

| # | Category | Task | Measures |
|---|----------|------|----------|
| A1 | Multi-Session | API Evolution (3 sessions: build API, add pagination, add rate limiting) | Success rate, design recall |
| A2 | Multi-Session | Bug History (2 sessions: fix race condition, similar bug elsewhere) | Fix speed, correctness |
| B | Preference Retention | Style Rules (3 sessions: "use dataclasses + pytest") | Preference adherence % |
| C | Cross-Project | Pattern Reuse (Project A: FastAPI CRUD, Project B: similar service) | Pattern reuse, completion time |

### A/B Design

- **Control:** MemoryDog with memory disabled (same LLM, same tools, fresh start each session)
- **Experimental:** MemoryDog with full memory + instincts
- Run once per condition (temp=0), fresh DB per run

### Metrics (5)

1. **Task Success Rate** — Pre-written test suite per task, pass/fail %
2. **Context Retention** — Checklist: "Did agent use X from prior session?" matches / total
3. **Preference Adherence** — Grep for violations (e.g., `from pydantic import`)
4. **Completion Time** — Wall clock from task start to passing tests
5. **Token Efficiency** — LiteLLM cost tracking, total tokens per task

### Expected Output

```
Task            | MEM OFF | MEM ON
────────────────┼─────────┼───────
API Evolution   | 67%     | 89%
Bug History     | 55%     | 82%
Style Rules     | 31%     | 94%
Pattern Reuse   | 48%     | 78%
```

Implementation: `tests/benchmarks/run.py` (~150 lines), `tests/benchmarks/tasks.py` (4 task definitions).

---

## 8. Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Dominant in AI/ML. Rich ecosystem. LLM calls dominate latency, not Python. |
| CLI Framework | Textual + Rich | Multi-pane TUI with live updates. Rich for formatting inside panes. |
| Web Framework | FastAPI | Async-native, Pydantic validation, auto OpenAPI docs. |
| LLM Provider | LiteLLM | Unified interface for 100+ providers. Zero provider-specific code. |
| Database | PostgreSQL 16 + pgvector | Single DB for relational + vector. FTS built in. No sync issues. |
| Cache | Redis | Session, retrieval, embedding caches. Industry standard. |
| Embeddings | OpenAI text-embedding-3-small | 1536d, $0.02/1M tokens, no GPU needed. |
| ORM | SQLAlchemy 2.0 + asyncpg | Async support, declarative models, Alembic migrations. |
| Task Queue | taskiq (initially) | Lightweight, async-native, Redis-backed. |
| Config | TOML (tomllib) | Python stdlib (3.11+), human-readable, ecosystem standard. |
| Package Mgmt | uv or poetry | Fast, lockfile support. |
| Testing | pytest + pytest-asyncio | Industry standard, fixtures, async. |
| Linting | ruff | Fast (Rust), replaces flake8 + isort + plugins. |

### Dependencies

```
textual, rich, litellm, httpx, fastapi, uvicorn,
sqlalchemy[asyncio], asyncpg, pgvector, alembic,
redis[hiredis], taskiq[redis], pydantic,
pydantic-settings, openai
```

---

## 9. Recruiter Impact

### Feature → Skill Mapping

| Feature | SWE | AI Eng | MLE |
|---------|-----|--------|-----|
| Client-server architecture | Systems design, API design | Distributed agent systems | — |
| PostgreSQL + pgvector schema | Database design, migrations | Vector DB, retrieval infra | Embedding storage, indexing |
| Hybrid retrieval + ranking | — | RAG systems, IR, reranking | Search/retrieval, embeddings |
| Memory lifecycle | — | Long-term memory architectures | Data lifecycle, summarization |
| Instincts (auto pattern learning) | — | Agent self-improvement | Unsupervised pattern discovery |
| Multi-provider LLM abstraction | Abstraction design | LLM infrastructure | Model selection/evaluation |
| Redis caching layers | Performance optimization | Latency-sensitive infra | — |
| Textual TUI | Developer tools, UX design | — | — |
| A/B benchmark framework | Testing, evaluation | Agent evaluation methodology | Experimental design |
| Multi-tenancy | Production database design | — | — |
| Background workers | Async processing, queues | Background agent pipelines | — |

### Resume Description

**MemoryDog** — *Python, FastAPI, PostgreSQL, pgvector, Redis, LiteLLM, Textual*

Designed and built a memory-augmented coding agent with persistent long-term memory across sessions, workspaces, and projects. Implemented a hybrid retrieval pipeline combining vector similarity (pgvector), BM25 keyword search, recency weighting, and importance scoring with configurable ranking formulas. Built an automatic memory lifecycle system (capture, rank, consolidate, archive) that prevents knowledge bloat while preserving high-value information. Designed an instinct subsystem that detects repeated user behavior patterns and automatically promotes them into reusable procedural modules that guide the agent's workflow. Built a multi-tenant client-server architecture with FastAPI, Redis caching, and background workers. Developed a Textual-based multi-pane TUI with real-time file preview, diff viewing, and tool execution monitoring. Achieved 89% context retention across multi-session tasks vs 67% for an equivalent stateless agent.

### Interview Talking Points by Role

**SWE:** Client-server decisions, 12-table schema design, FastAPI API design, 4-layer Redis caching, background worker architecture, testing methodology.

**AI Engineering:** Agent loop + tool execution, multi-provider LLM abstraction, hybrid retrieval + reranking, agent self-improvement via instincts, long-term memory architecture, prompt construction and context management.

**MLE:** Embedding pipeline design, hybrid ranking with tunable weights, importance + confidence scoring, unsupervised pattern discovery from behavioral data, A/B evaluation methodology, vector search with HNSW indexes.

---

## 10. Folder Structure (Full Vision)

```
memorydog/
├── cli/                    # Textual TUI client
│   ├── app.py
│   ├── agent_loop.py
│   ├── memory_client.py
│   ├── commands/
│   │   └── instinct.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── read.py
│   │   ├── write.py
│   │   ├── edit.py
│   │   ├── bash.py
│   │   ├── glob.py
│   │   ├── grep.py
│   │   └── memory_search.py
│   ├── provider/
│   │   └── litellm_provider.py
│   ├── prompts/
│   │   └── system.py
│   └── ui/
│       └── chat_screen.py
├── server/                 # FastAPI backend
│   ├── main.py
│   ├── db.py
│   ├── tasks.py
│   ├── api/
│   │   ├── users.py
│   │   ├── workspaces.py
│   │   ├── memories.py
│   │   ├── retrieve.py
│   │   ├── conversations.py
│   │   └── instincts.py
│   ├── models/
│   │   ├── user.py
│   │   ├── workspace.py
│   │   ├── memory.py
│   │   ├── memory_tag.py
│   │   ├── memory_relation.py
│   │   ├── conversation.py
│   │   ├── conversation_turn.py
│   │   ├── retrieval_event.py
│   │   ├── instinct.py
│   │   ├── instinct_trigger.py
│   │   ├── instinct_version.py
│   │   ├── instinct_activation.py
│   │   └── behavioral_pattern.py
│   ├── services/
│   │   ├── retrieval.py
│   │   ├── ranking.py
│   │   ├── embedding.py
│   │   ├── extraction.py
│   │   ├── dedup.py
│   │   ├── summarize.py
│   │   ├── contradiction.py
│   │   ├── instinct_engine.py
│   │   ├── pattern_detector.py
│   │   └── instinct_generator.py
│   └── workers/
│       ├── extraction_worker.py
│       ├── consolidation.py
│       ├── decay.py
│       ├── reflection.py
│       └── instinct_worker.py
├── shared/                 # Types, schemas, utils
│   └── schemas.py
├── migrations/             # Alembic
│   ├── 001_initial.sql
│   ├── 002_fts_confidence.sql
│   ├── 003_tags_relations_conversations.sql
│   ├── 004_lifecycle.sql
│   └── 005_instincts.sql
├── tests/
│   ├── unit/
│   ├── integration/
│   └── benchmarks/
│       ├── run.py
│       ├── tasks.py
│       └── README.md
├── docker-compose.yml
├── pyproject.toml
└── README.md
```
