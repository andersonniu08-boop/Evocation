"""Integration tests for the full memory pipeline."""

from core.agent_loop import AgentState, dog_status, pop_status, run_turn
from core.provider import Message, MockProvider


class RecordingProvider(MockProvider):
    """Provider that records all calls for verification."""

    def __init__(self):
        super().__init__()
        self.calls: list[list[Message]] = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return super().chat(messages, tools)


async def test_full_pipeline_with_mock_provider():
    """End-to-end: user input → instincts → retrieval attempt → LLM → response."""
    provider = RecordingProvider()
    state = AgentState(workspace="test-project")

    resp = await run_turn(provider, state, "There is a race condition bug")

    assert resp
    assert len(provider.calls) >= 1
    assert len(state.history) >= 1
    # Bug Hunter should have activated
    assert "Bug Hunter" in state.active_instincts
    # Verify the system prompt contains instinct injection
    system_msg = provider.calls[0][0].content if provider.calls[0] else ""
    assert "Bug Hunter" in system_msg or "tools" in system_msg.lower()


async def test_multi_turn_history():
    """Multiple turns accumulate history correctly."""
    provider = MockProvider()
    state = AgentState(workspace="test")

    await run_turn(provider, state, "Hello")
    await run_turn(provider, state, "Add a benchmark for the neural network")

    assert len(state.history) >= 2
    # Turn 2 should have activated AI Evaluation Expert
    assert "AI Evaluation Expert" in state.active_instincts


async def test_instinct_not_activated_for_unrelated():
    """Instincts should NOT activate for unrelated queries."""
    provider = MockProvider()
    state = AgentState(workspace="random")

    await run_turn(provider, state, "What time is it?")

    assert len(state.active_instincts) == 0


async def test_dog_status_messages():
    """Dog status messages should be populated during pipeline."""
    provider = MockProvider()
    state = AgentState(workspace="test")

    dog_status("")
    pop_status()

    await run_turn(provider, state, "fix the deadlock bug")

    msgs = pop_status()
    assert any("Bug Hunter" in m for m in msgs)
    assert any("Fetching" in m for m in msgs)


async def test_memory_search_tool_integration():
    """memory_search tool should be callable via execute_tool and return stub."""
    from core.tools import execute_tool

    result = execute_tool("memory_search", {"query": "race condition"})
    assert result["success"]
    assert "memories" in result


async def test_agent_state_persistence():
    """AgentState maintains workspace and instincts across turns."""
    state = AgentState(workspace="my-project")
    assert state.workspace == "my-project"

    provider = MockProvider()
    await run_turn(provider, state, "fix the bug in task queue")
    assert "Bug Hunter" in state.active_instincts

    await run_turn(provider, state, "hello")
    # Now should be empty since "hello" matches no triggers
    assert len(state.active_instincts) == 0
