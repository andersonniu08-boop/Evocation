"""Tests for MemoryDog core and CLI."""
import sys

from core.agent_loop import AgentState, run_turn
from core.context import build_messages, build_system_prompt
from core.provider import Message, MockProvider
from core.tools import TOOL_REGISTRY, execute_tool, get_tool_definitions


def test_mock_provider_returns_response():
    provider = MockProvider()
    messages = [Message(role="user", content="Hello")]
    response = provider.chat(messages)
    assert response.content
    assert isinstance(response.content, str)
    assert len(response.content) > 0


def test_build_system_prompt():
    prompt = build_system_prompt(workspace="test-project")
    assert "coding agent" in prompt.lower()
    assert "tools" in prompt.lower()


def test_build_messages_appends_history():
    history = [Message(role="user", content="hi"), Message(role="assistant", content="hey")]
    msgs = build_messages(history=history, user_input="do stuff")
    assert msgs[0].role == "system"
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "do stuff"


def test_get_tool_definitions_returns_list():
    defs = get_tool_definitions()
    assert isinstance(defs, list)
    assert len(defs) >= 6
    for d in defs:
        assert "name" in d
        assert "description" in d


def test_tool_registry_has_all_tools():
    assert "read" in TOOL_REGISTRY
    assert "write" in TOOL_REGISTRY
    assert "edit" in TOOL_REGISTRY
    assert "bash" in TOOL_REGISTRY
    assert "glob" in TOOL_REGISTRY
    assert "grep" in TOOL_REGISTRY


def test_execute_read_returns_file_content(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    result = execute_tool("read", {"filePath": str(f)})
    assert result["success"]
    assert "hello world" in result["content"]


def test_run_turn_returns_response():
    provider = MockProvider()
    state = AgentState()
    response = run_turn(provider, state, "Hello")
    assert response
    assert "Hello" in response or "I'm MemoryDog" in response
    assert len(state.history) >= 1


def test_run_turn_maintains_history():
    provider = MockProvider()
    state = AgentState()
    run_turn(provider, state, "hi")
    run_turn(provider, state, "what's up")
    assert len(state.history) >= 2


def test_cli_help_runs():
    old = sys.argv
    sys.argv = ["dog", "--help"]
    try:
        from cli.main import main

        main()
    except SystemExit:
        pass
    finally:
        sys.argv = old


async def test_chat_screen_exists():
    from cli.ui.chat import ChatScreen

    screen = ChatScreen(workspace="test-project")
    assert screen is not None
    assert screen.workspace == "test-project"
