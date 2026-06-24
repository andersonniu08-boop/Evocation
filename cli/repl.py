"""Raw terminal REPL — linear scroll, no full-screen TUI."""

import asyncio
import json
import os
import sys
from contextlib import suppress

from core.agent_loop import AgentState, init_agent, run_turn
from core.logger import init_logger
from core.provider import BaseProvider, LiteLLMProvider, MockProvider


async def run_repl(
    workspace: str = ".",
    provider: BaseProvider | None = None,
    model_name: str = "unknown",
):
    """Run a simple read-eval-print loop in the terminal."""
    init_logger(workspace)

    try:
        state = await init_agent(workspace)
    except Exception:
        ws_name = os.path.basename(os.path.abspath(workspace)) or workspace
        state = AgentState(workspace=ws_name)
        print("[warning: database unavailable]")

    provider = provider or MockProvider()

    print(f"Evocation ({model_name})\n")

    # Welcome
    try:
        from core.memory import count_memories

        count = await count_memories(state.workspace)
        if count > 0:
            print(f"{count} memories from previous sessions")
    except Exception:
        pass

    print("Type /help for commands, Ctrl+C to quit.\n")

    while True:
        try:
            line = await _async_input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        text = line.strip()
        if not text:
            continue

        # Slash commands
        if text.startswith("/"):
            _handle_command(text, state)
            continue

        # Normal chat turn
        print(f"\nYou: {text}")

        response = ""
        try:
            response = await run_turn(
                provider,
                state,
                text,
                on_status=lambda msg: print(f"  [{msg}]"),
                on_token=lambda token: sys.stdout.write(token),
            )
        except Exception as e:
            print(f"\nError: {e}")

        if response and not response.startswith("❌"):
            print()  # newline after streaming
        elif response:
            print(f"\n{response}")

        sys.stdout.flush()


async def _async_input(prompt: str) -> str:
    """Non-blocking input using asyncio thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, input, prompt)


def _handle_command(text: str, state: AgentState):
    """Handle slash commands inline."""
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/help":
        print("Commands: /help /model /status /clear /quit /plan /execute")
        print("  /plan <objective>  — Generate a task plan from an objective")
        print("  /execute <goal_id>  — Execute all pending tasks for a goal")
    elif cmd == "/quit":
        raise KeyboardInterrupt()
    elif cmd == "/status":
        print(f"Workspace: {state.workspace}")
        print(f"History: {len(state.history)} messages")
    elif cmd == "/clear":
        state.history.clear()
        print("Context cleared.")
    elif cmd == "/model":
        print(f"Active model: {arg or 'unchanged'}")
    elif cmd == "/plan":
        if not arg.strip():
            print("Usage: /plan <objective>")
        else:
            asyncio.create_task(_cli_plan(arg))
    elif cmd == "/execute":
        if not arg.strip():
            print("Usage: /execute <goal_id>")
        else:
            asyncio.create_task(_cli_execute(arg))
    else:
        print(f"Unknown command: {cmd}")


async def _cli_approval(tool_name: str, params: dict, reasoning: str) -> bool:
    """CLI-side approval handler — prompts user inline for destructive tools."""
    params_str = json.dumps(params, indent=2)[:300]
    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  [EVOCATION REQUIRES APPROVAL]           ║")
    print(f"  ║  Tool: {tool_name:<34}║")
    print(f"  ║  Reason: {reasoning[:40]:<32}║")
    print(f"  ╚══════════════════════════════════════════╝")
    print(f"  Params: {params_str}")

    try:
        answer = await _async_input(f"  Approve? (y/n): ")
        return answer.strip().lower().startswith("y")
    except (EOFError, KeyboardInterrupt):
        return False


async def _cli_plan(objective: str):
    """Generate a plan for an objective via CLI."""
    try:
        from core.config import load_config
        from core.planning import generate_plan
        from core.provider import create_provider

        config = load_config()
        provider = create_provider(config)
        print(f"\nPlanning for: {objective}")
        tasks = await generate_plan(objective, provider)
        print(f"\nGenerated {len(tasks)} tasks:")
        for t in tasks:
            print(f"  {t['order']}. {t['description']}")
        print()
    except Exception as e:
        print(f"Plan error: {e}")


async def _cli_execute(goal_id: str):
    """Execute all pending tasks for a goal via CLI."""
    try:
        from core.config import load_config
        from core.db import get_pool
        from core.executor import execute_goal
        from core.provider import create_provider

        pool = await get_pool()
        async with pool.acquire() as conn:
            goal_row = await conn.fetchrow("SELECT * FROM goals WHERE id = $1", goal_id)
            if not goal_row:
                print(f"Goal not found: {goal_id}")
                return
            task_rows = await conn.fetch(
                'SELECT * FROM tasks WHERE goal_id = $1 ORDER BY "order"', goal_id
            )

        goal = dict(goal_row)
        tasks = [dict(r) for r in task_rows]
        pending = [t for t in tasks if t.get("status") not in ("completed", "failed")]

        if not pending:
            print("No pending tasks.")
            return

        config = load_config()
        provider = create_provider(config)

        print(f"\nExecuting goal: {goal.get('title', 'Untitled')}")
        print(f"Pending tasks: {len(pending)}/{len(tasks)}\n")

        result = await execute_goal(
            goal, tasks, provider,
            on_status=lambda msg: print(f"  {msg}"),
            on_approval=_cli_approval,
        )

        # Save task statuses
        async with pool.acquire() as conn:
            for t in tasks:
                await conn.execute(
                    "UPDATE tasks SET status = $1, findings = $2 WHERE id = $3",
                    t.get("status", "pending"), t.get("findings", ""), t["id"],
                )

        print(f"\nDone. {result['completed']} completed, {result['failed']} failed.")
    except Exception as e:
        print(f"Execute error: {e}")
