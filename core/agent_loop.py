"""Core agent execution loop."""
from dataclasses import dataclass, field

from core.context import build_messages
from core.provider import BaseProvider, Message
from core.tools import execute_tool, get_tool_definitions


@dataclass
class AgentState:
    history: list[Message] = field(default_factory=list)
    workspace: str = "."
    conversation_id: str | None = None


def run_turn(
    provider: BaseProvider,
    state: AgentState,
    user_input: str,
) -> str:
    messages = build_messages(history=state.history, user_input=user_input)
    tools = get_tool_definitions()
    response = provider.chat(messages, tools=tools)

    if response.tool_calls:
        tool_results = []
        for tc in response.tool_calls:
            result = execute_tool(tc["name"], tc.get("parameters", {}))
            tool_results.append({"tool_call_id": tc.get("id", ""), "result": result})
        state.history.append(Message(role="assistant", content=response.content))
        state.history.append(Message(role="tool", content=str(tool_results)))

        followup = build_messages(history=state.history, user_input="Tool results above. Continue.")
        response2 = provider.chat(followup, tools=[])
        state.history.append(Message(role="assistant", content=response2.content))
        return response2.content

    state.history.append(Message(role="assistant", content=response.content))
    return response.content
