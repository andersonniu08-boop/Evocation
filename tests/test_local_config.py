"""Tests for local model config and fallback routing."""
import tomllib

from core.config import (
    DEFAULT_CONFIG,
    Config,
    LocalConfig,
    load_config,
    save_config,
)
from core.provider import create_provider


class TestLocalConfig:
    def test_defaults(self):
        cfg = LocalConfig()
        assert cfg.endpoint == "http://localhost:11434"
        assert cfg.primary_model == "phi4-mini"
        assert cfg.fallback_model == "llama3.2"
        assert cfg.context_window == 8192

    def test_default_config_has_local_section(self):
        data = tomllib.loads(DEFAULT_CONFIG)
        assert "local" in data
        assert data["local"]["primary_model"] == "phi4-mini"
        assert data["local"]["fallback_model"] == "llama3.2"
        assert data["local"]["endpoint"] == "http://localhost:11434"

    def test_config_loads_local(self, tmp_path, monkeypatch):
        import core.config as config_module

        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / ".evocation")
        monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / ".evocation" / "config.toml")

        config = config_module.create_default_config()
        assert config.local.primary_model == "phi4-mini"
        assert config.local.fallback_model == "llama3.2"
        assert config.local.endpoint == "http://localhost:11434"

    def test_save_config_includes_local(self, tmp_path, monkeypatch):
        import core.config as config_module

        monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path / ".evocation")
        monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / ".evocation" / "config.toml")

        cfg = Config()
        cfg.local.primary_model = "custom-model"
        cfg.local.fallback_model = "backup-model"
        save_config(cfg)

        loaded = load_config()
        assert loaded.local.primary_model == "custom-model"
        assert loaded.local.fallback_model == "backup-model"


class TestProviderRouting:
    def test_ollama_provider_created_for_local(self):
        config = Config()
        config.provider.provider_type = "ollama"
        config.provider.model = "phi4-mini"
        config.local.endpoint = "http://localhost:11434"

        provider = create_provider(config)
        from core.provider import OllamaProvider

        assert isinstance(provider, OllamaProvider)
        assert provider.model == "phi4-mini"
        assert provider.endpoint == "http://localhost:11434"

    def test_litellm_provider_created_for_cloud(self):
        config = Config()
        config.provider.provider_type = "litellm"
        config.provider.model = "deepseek/deepseek-chat"

        provider = create_provider(config)
        from core.provider import LiteLLMProvider

        assert isinstance(provider, LiteLLMProvider)
        assert provider.model == "deepseek/deepseek-chat"

    def test_provider_model_override(self):
        config = Config()
        config.provider.provider_type = "ollama"
        config.provider.model = "phi4-mini"

        provider = create_provider(config)
        assert provider.model == "phi4-mini"

        provider.model = "llama3.2"
        assert provider.model == "llama3.2"


class TestFallbackLogic:
    def test_is_chat_error(self):
        from core.bridge import _is_chat_error

        assert _is_chat_error("❌ Connection refused") is True
        assert _is_chat_error("Something error: ollama down") is True
        assert _is_chat_error("Hello world") is False
        assert _is_chat_error("") is False
        assert _is_chat_error("Normal response about errors in code") is False

    def test_fallback_from_config(self):
        config = Config()
        config.local.primary_model = "phi4-mini"
        config.local.fallback_model = "llama3.2"
        config.provider.model = "phi4-mini"
        config.provider.provider_type = "ollama"

        assert config.local.fallback_model == "llama3.2"
        # Verify fallback is different from primary
        assert config.local.fallback_model != config.provider.model
