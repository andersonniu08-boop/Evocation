"""MemoryDog CLI entry point."""
import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="dog", description="MemoryDog \u2014 memory-augmented coding agent"
    )
    sub = parser.add_subparsers(dest="command")

    chat_parser = sub.add_parser("chat", help="Start interactive chat session")
    chat_parser.add_argument("-w", "--workspace", default=".", help="Workspace path")

    config_parser = sub.add_parser("config", help="Configure MemoryDog")
    config_parser.add_argument("--provider", help="LLM provider")
    config_parser.add_argument("--model", help="Model name")
    config_parser.add_argument("--api-key", help="API key")

    args = parser.parse_args()

    if args.command == "chat":
        from cli.app import MemoryDogApp

        app = MemoryDogApp(workspace=args.workspace)
        app.run()
    elif args.command == "config":
        print(
            "Config not yet implemented. Edit ~/.memorydog/config.toml directly."
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
