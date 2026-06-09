# MemoryDog — VS Code Extension

A memory-augmented coding agent that remembers past conversations, design decisions,
bugs, and project history across sessions. Unlike stateless agents, MemoryDog gets
better the longer you work with it.

## Quick Install

1. Download `memorydog-0.1.0.vsix` from the releases page
2. Install in VS Code:

```bash
code --install-extension memorydog-0.1.0.vsix
```

Or via VS Code UI: Extensions → "..." → "Install from VSIX..."

## Getting Started

1. Install the extension
2. Click the 🐕 icon in the Activity Bar
3. Open the **Chat** panel
4. Enter your API key when prompted (or set it in VS Code Settings → `memorydog.apiKey`)
5. Start chatting — MemoryDog remembers conversations across sessions

## Requirements

- **Python 3.11+** with MemoryDog installed (`pip install -e .` from the repo root)
- **PostgreSQL 16 + pgvector** — run `docker compose up` from the repo root
- **Ollama** with `nomic-embed-text` — `ollama pull nomic-embed-text`
- **VS Code** 1.85.0 or later

## Features

- **💬 Chat** — Full conversation with streaming responses, status updates, and tool execution
- **📚 Memory Browser** — Browse persistent memories from PostgreSQL, filter by workspace
- **⚡ Instinct Viewer** — View loaded instincts from `~/.memorydog/instincts.toml`
- **🐕 Animated Mascot** — CSS dog with idle, sniffing, excited, and sleeping states
- **📊 Status Bar** — Live memory count, instinct count, workspace awareness

## Configuration

Set your API key in VS Code Settings (`Cmd+,`):

- `memorydog.apiKey` — Your LLM provider API key
- `memorydog.model` — LiteLLM model string (default: `deepseek/deepseek-chat`)

Or run `dog config` in the terminal for the interactive wizard.

## Building from Source

```bash
cd vscode
npm install
npm run compile
npx @vscode/vsce package
code --install-extension memorydog-0.1.0.vsix
```

## Architecture

```
VS Code Extension (TypeScript)
  ├── Chat panel (webview)      ← primary UI
  ├── Memory browser (webview)  ← live PostgreSQL data
  ├── Instinct viewer (webview) ← TOML instinct config
  └── Dog mascot (webview)      ← animated status indicator
        │
        │ JSON-RPC over stdin/stdout
        ▼
Python Core (memorydog-core)
  ├── Agent loop, tools (7), provider (LiteLLM)
  ├── Memory CRUD, extraction, embeddings (Ollama)
  ├── Hybrid retrieval (vector + FTS + ranking)
  └── Instinct engine (TOML triggers + bias)
        │
        │ asyncpg
        ▼
PostgreSQL 16 + pgvector
```

The extension communicates with the Python core via `dog serve` — a local
JSON-RPC subprocess. No HTTP server, no Redis, no background workers.
