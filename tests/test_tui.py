"""Tests for MemoryDog core and CLI."""
import sys

from core.agent_loop import AgentState, run_turn
from core.config import Config
from core.context import build_messages, build_system_prompt
from core.provider import LiteLLMProvider, Message, MockProvider
from core.tools import TOOL_REGISTRY, execute_tool, get_tool_definitions


def test_mock_provider_returns_response():
    provider = MockProvider()
    messages = [Message(role="user", content="Hello")]
    response = provider.chat(messages)
    assert response.content
    assert isinstance(response.content, str)
    assert len(response.content) > 0


def test_mock_provider_tracks_tokens():
    provider = MockProvider()
    provider.chat([Message(role="user", content="test")])
    assert provider.last_tokens >= 0


def test_litellm_provider_instantiation():
    provider = LiteLLMProvider(
        model="claude-sonnet-4-20250514",
        api_key="test-key",
    )
    assert provider.model == "claude-sonnet-4-20250514"
    assert provider.last_tokens == 0


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


async def test_run_turn_returns_response():
    provider = MockProvider()
    state = AgentState()
    response = await run_turn(provider, state, "Hello")
    assert response
    assert "Hello" in response or "I'm MemoryDog" in response
    assert len(state.history) >= 1


async def test_run_turn_maintains_history():
    provider = MockProvider()
    state = AgentState()
    await run_turn(provider, state, "hi")
    await run_turn(provider, state, "what's up")
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

    screen = ChatScreen(workspace="test-project", model_name="test-model")
    assert screen is not None
    assert screen.workspace == "test-project"
    assert screen.model_name == "test-model"


def test_config_defaults():
    config = Config()
    assert "claude" in config.provider.model
    assert "text-embedding" in config.embedding.model
    assert config.database.url


def test_config_load_creates_file(tmp_path, monkeypatch):
    import core.config as config_module

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / ".memorydog")
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / ".memorydog" / "config.toml")

    cfg = config_module.create_default_config()
    assert "claude" in cfg.provider.model
    assert (tmp_path / ".memorydog" / "config.toml").exists()


def test_make_mock_provider():
    from cli.main import _make_mock_provider

    provider = _make_mock_provider()
    from core.provider import MockProvider

    assert isinstance(provider, MockProvider)


def test_ranking_formula():
    from core.ranking import score_memory

    s = score_memory(
        vector_score=0.8,
        bm25_score=0.6,
        days_since_access=0,
        importance=0.9,
        decay_factor=1.0,
        same_workspace=True,
        access_count=10,
        mean_access_count=5.0,
    )
    assert 0 < s < 1.5


def test_ranking_penalizes_old_memories():
    from core.ranking import score_memory

    recent = score_memory(0.8, 0.6, 0, 0.5, 1.0, True, 5, 5.0)
    old = score_memory(0.8, 0.6, 100, 0.5, 1.0, True, 5, 5.0)
    assert recent > old


def test_ranking_boosts_same_workspace():
    from core.ranking import score_memory

    same = score_memory(0.8, 0.6, 0, 0.5, 1.0, True, 5, 5.0)
    diff = score_memory(0.8, 0.6, 0, 0.5, 1.0, False, 5, 5.0)
    assert same > diff


def test_load_instincts():
    from core.instincts import load_instincts

    instincts = load_instincts()
    assert len(instincts) >= 3
    names = [i.name for i in instincts]
    assert "Bug Hunter" in names
    assert "AI Evaluation Expert" in names


def test_match_instincts():
    from core.instincts import load_instincts, match_instincts

    instincts = load_instincts()
    matched = match_instincts(instincts, "there is a race condition bug", "test-project")
    assert len(matched) > 0
    assert matched[0][0].name == "Bug Hunter"


def test_instinct_no_match():
    from core.instincts import load_instincts, match_instincts

    instincts = load_instincts()
    matched = match_instincts(instincts, "hello world", "test-project")
    assert len(matched) == 0
