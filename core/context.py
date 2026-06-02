"""Prompt construction."""

from core.provider import Message

SYSTEM_PROMPT = """You are MemoryDog, a coding agent with persistent memory.

You have access to tools for reading, writing, editing files,
running commands, and searching your memory.

Current workspace: {workspace}

Be direct and concise. Use tools when you need to read or modify code.
"""


def build_system_prompt(workspace: str) -> str:
    return SYSTEM_PROMPT.format(workspace=workspace)


def build_messages(history: list[Message], user_input: str) -> list[Message]:
    msgs = [Message(role="system", content=build_system_prompt(workspace="."))]
    if history:
        msgs.extend(history)
    msgs.append(Message(role="user", content=user_input))
    return msgs
