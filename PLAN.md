# Evocation — Implementation Plan

## Phase 0: Stabilize & Freeze ✅

- [x] Fix config defaults (Ollama + phi4-mini)
- [x] Resolve `name 'json' is not defined` in provider.py
- [x] Fix state machine: Error state shows instead of Ready after failures
- [x] Verify local models work (phi4-mini, llama3.2)
- [x] Verify all 7 tools execute correctly
- [x] Tag `memorydog-v1` for archival

## Phase 1: Rebrand ✅

- [x] Global find-and-replace: MemoryDog → Evocation
- [x] Sidebar panel: Memories → Knowledge
- [x] Package name: memorydog → evocation
- [x] Documentation: AGENTS.md, DESIGN.md, PLAN.md
- [x] Spec file renamed: memorydog-mvp.md → evocation-mvp.md
- [x] VS Code extension metadata updated

## Phase 2: Goals ✅

- [x] PostgreSQL schema: `goals` table (id, title, objective, status, progress)
- [x] `conversations.goal_id` FK (nullable)
- [x] Goal CRUD RPC: get_goals, create_goal, update_goal, get_goal
- [x] TypeScript: Goal interface, GoalStatus type, bridge methods

## Phase 3: Planner ✅

- [x] `core/planning.py` — Planner module
- [x] System prompt: senior architect persona, strict JSON output
- [x] `generate_plan(objective, provider)` — LLM → Task list
- [x] Retry logic (3 attempts) for malformed JSON
- [x] RPC: generate_plan
- [x] TypeScript: Task interface, bridge.generatePlan()

## Phase 4: Task System

- [ ] Database table: `tasks` (id, goal_id, description, status, order, started_at, completed_at)
- [ ] Task CRUD RPC
- [ ] Task linked to goal plan
- [ ] Findings table: `findings` (id, task_id, content, type, created_at)
- [ ] Notes table: `notes` (id, goal_id, content, created_at)

## Phase 5: Memory Upgrade

- [ ] Goal-oriented retrieval bias — prioritize architectural decisions, past plans, failures
- [ ] Weight adjustments for goal-relevant memories
- [ ] Goal context injection into system prompt
- [ ] Memory dedup refinements

## Phase 6: Goal Dashboard

- [ ] Rebuild VS Code webview UI for Goal tracking
- [ ] Sidebar: Sessions (primary, top), Goals (secondary), Context (bottom)
- [ ] Goal list with status badges in sidebar
- [ ] Goal detail editor tab: objective, plan checklist, activity feed
- [ ] Progress visualization
- [ ] Task completion toggles

## Phase 7: Execution Mode

- [ ] Autonomous loop: iterate tasks, run tools, record findings
- [ ] **Auto-start execution** — plan executes immediately after generation (no editing phase)
- [ ] User-selectable autonomy levels:
  - **Safe:** Ask before every tool call
  - **Standard (default):** Auto-run read/glob/grep/memory_search; halt on bash/write/edit
  - **Full auto:** Run entire plan; user can pause/abort
- [ ] Real-time activity feed
- [ ] Error handling: task failure → halt or skip decision
- [ ] Goal status auto-update (pending → in_progress → completed → failed)

## Current Status

**125 tests passing.** Core infrastructure (pgvector, tool execution, session state, local LLM) is solid. The Planner generates task plans from goals. The remaining work is the execution loop, task persistence, and the Goal Dashboard UI.
