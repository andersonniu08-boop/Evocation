"""MemoryDog CLI entry point."""
import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="dog", description="MemoryDog \u2014 memory-augmented coding agent"
    )
    sub = parser.add_subparsers(dest="command")

    chat_parser = sub.add_parser("chat", help="Start interactive chat session")
    chat_parser.add_argument("-w", "--workspace", default=".", help="Workspace path")
    chat_parser.add_argument(
        "-m", "--model", help="Override model from config"
    )
    chat_parser.add_argument(
        "--mock", action="store_true", help="Use mock provider (no API needed)"
    )

    sub.add_parser("config", help="Interactive configuration wizard")

    sub.add_parser("status", help="Show MemoryDog status")

    instinct_parser = sub.add_parser("instinct", help="Manage instincts")
    instinct_sub = instinct_parser.add_subparsers(dest="instinct_cmd")
    instinct_sub.add_parser("list", help="List all instincts")
    show_parser = instinct_sub.add_parser("show", help="Show instinct details")
    show_parser.add_argument("name", help="Instinct name")
    edit_parser = instinct_sub.add_parser("edit", help="Open instincts file in editor")
    edit_parser.add_argument(
        "--editor", help="Editor command (default: $EDITOR or nano)"
    )

    args = parser.parse_args()

    if args.command == "chat":
        from core.config import load_config

        config = load_config()

        if args.mock:
            provider = _make_mock_provider()
            model_name = "mock"
        else:
            provider, model_name = _make_provider_from_config(config, args.model)

        from cli.app import MemoryDogApp

        app = MemoryDogApp(
            workspace=args.workspace, provider=provider, model_name=model_name
        )
        app.run()

    elif args.command == "config":
        _run_config_wizard()

    elif args.command == "status":
        _run_status()

    elif args.command == "instinct":
        _run_instinct_cmd(args)

    else:
        parser.print_help()


def _make_mock_provider():
    from core.provider import MockProvider

    return MockProvider()


def _make_provider_from_config(config, model_override=None):
    from core.provider import LiteLLMProvider

    pc = config.provider
    model = model_override or pc.model

    provider = LiteLLMProvider(
        model=model,
        api_key=pc.api_key,
        api_base=pc.api_base or None,
    )
    return provider, model


def _run_config_wizard():
    from core.config import (
        Config,
        load_config,
        save_config,
    )

    try:
        config = load_config()
    except Exception:
        config = Config()

    print("\n\U0001F415 MemoryDog Configuration\n")
    print("Use LiteLLM model format: provider/model")
    print("Examples: anthropic/claude-sonnet-4-20250514, openai/gpt-4o, ollama/llama3\n")
    print("Press Enter to keep current values.\n")

    model = input(f"Model [{config.provider.model}]: ").strip()
    if model:
        config.provider.model = model

    api_key = input(f"API Key [{_mask(config.provider.api_key)}]: ").strip()
    if api_key:
        config.provider.api_key = api_key

    api_base = input(
        f"API Base / custom URL (optional) [{config.provider.api_base or 'none'}]: "
    ).strip()
    if api_base:
        config.provider.api_base = api_base

    embed_model = input(
        f"\nEmbedding model [{config.embedding.model}]: "
    ).strip()
    if embed_model:
        config.embedding.model = embed_model

    save_config(config)
    print("\n\U0001F415 Config saved to ~/.memorydog/config.toml")
    print("Run 'dog chat' to start.")
    print("Run 'dog instinct list' to see your instincts.")


def _run_instinct_cmd(args):

    from core.instincts import ensure_instincts_file, load_instincts

    ensure_instincts_file()

    if args.instinct_cmd == "list":
        instincts = load_instincts()
        if not instincts:
            print("\U0001F415 No instincts found.")
            return
        print("\n\U0001F415 Instincts\n")
        for i, inst in enumerate(instincts, 1):
            triggers = ", ".join(inst.triggers)
            print(f"  {i}. {inst.name}")
            print(f"     {inst.description}")
            print(f"     Triggers: {triggers}\n")
        print(f"Total: {len(instincts)} instincts")
        print("Edit: dog instinct edit")

    elif args.instinct_cmd == "show":
        instincts = load_instincts()
        name_lower = args.name.lower()
        for inst in instincts:
            if inst.name.lower() == name_lower:
                print(f"\n\U0001F415 {inst.name}\n")
                print(f"  Description: {inst.description}")
                print(f"  Triggers: {', '.join(inst.triggers)}")
                print(f"  Retrieval bias: {', '.join(inst.retrieval_bias)}")
                print(f"\n  Prompt:\n    {inst.prompt}")
                return
        print(f"No instinct named '{args.name}' found.")

    elif args.instinct_cmd == "edit":
        import os
        import subprocess

        editor = args.editor or os.environ.get("EDITOR") or \
                 os.environ.get("VISUAL") or "nano"
        path = str(ensure_instincts_file())
        subprocess.call([editor, path])

    else:
        print("Usage: dog instinct [list|show <name>|edit]")


def _run_status():
    from core.config import load_config
    from core.instincts import load_instincts

    try:
        config = load_config()
    except Exception:
        print("No config found. Run 'dog config' first.")
        return

    instincts = load_instincts()

    print("\n\U0001F415 MemoryDog Status\n")
    print(f"  Provider: {config.provider.model}")
    print(f"  Embedding: {config.embedding.model}")
    print(f"  Database: {config.database.url[:50]}...")
    print(f"  Instincts: {len(instincts)} loaded")
    print("  Config: ~/.memorydog/config.toml")
    print("  Instincts file: ~/.memorydog/instincts.toml")

    if not config.provider.api_key:
        print("\n  \u26a0 No API key set. Run 'dog config' to configure.")
    else:
        masked = config.provider.api_key[:4] + "..." + config.provider.api_key[-4:]
        print(f"  API Key: {masked}")


def _mask(key: str) -> str:
    if not key or len(key) < 8:
        return "(not set)"
    return key[:4] + "..." + key[-4:]


if __name__ == "__main__":
    main()
