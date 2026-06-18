"""Raw terminal REPL — linear scroll, no full-screen TUI."""

import asyncio
import os
import sys
from contextlib import suppress

from core.agent_loop import AgentState, init_agent, run_turn
from core.provider import BaseProvider, LiteLLMProvider, MockProvider


async def run_repl(
    workspace: str = ".",
    provider: BaseProvider | None = None,
    model_name: str = "unknown",
):
    """Run a simple read-eval-print loop in the terminal."""
    state = await init_agent(workspace)

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
        print("Commands: /help /model /status /clear /quit")
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
    else:
        print(f"Unknown command: {cmd}")
