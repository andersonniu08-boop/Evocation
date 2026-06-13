import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { MemoryDogBridge } from "./bridge";
import { DOG_SPRITE_SHEET, SPRITE, DOG_STATES, FRAME_DURATIONS } from "./assets";

let bridge: MemoryDogBridge;
let statusBarItem: vscode.StatusBarItem;
let chatPanel: vscode.WebviewPanel | undefined;
let lastRetrievedMemoryIds: string[] = [];

function sendToChat(msg: any) {
  chatPanel?.webview.postMessage(msg);
}

export function activate(context: vscode.ExtensionContext) {
  // ── Status Bar ──────────────────────────────────────────
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = "$(paw) MemoryDog";
  statusBarItem.tooltip = "MemoryDog — memory-augmented coding agent";
  statusBarItem.command = "memorydog.openChat";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // ── Bridge ──────────────────────────────────────────────
  bridge = new MemoryDogBridge();
  startBridgeAsync();

  // ── Sidebar: Memory Panel ────────────────────────────────
  const memoryProvider = new MemoryPanelProvider(context.extensionUri, bridge);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("memorydog.memoryPanel", memoryProvider)
  );

  // ── Sidebar: Instinct Panel ──────────────────────────────
  const instinctProvider = new InstinctPanelProvider(context.extensionUri, bridge);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("memorydog.instinctPanel", instinctProvider)
  );

  // ── Commands ────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("memorydog.openChat", () => createChatPanel(context.extensionUri)),
    vscode.commands.registerCommand("memorydog.focusChat", () => vscode.commands.executeCommand("memorydog.openChat")),
    vscode.commands.registerCommand("memorydog.configure", configureApiKey),
    vscode.commands.registerCommand("memorydog.showQuickActions", showQuickActions),
    // Legacy
    vscode.commands.registerCommand("memorydog.start", () => vscode.commands.executeCommand("memorydog.openChat")),
    vscode.commands.registerCommand("memorydog.startChat", () => vscode.commands.executeCommand("memorydog.openChat")),
    vscode.commands.registerCommand("memorydog.showMemoryPanel", () => vscode.commands.executeCommand("memorydog.memoryPanel.focus")),
    vscode.commands.registerCommand("memorydog.showInstinctPanel", () => vscode.commands.executeCommand("memorydog.instinctPanel.focus")),
  );

  // ── Config change listener ──────────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("memorydog.apiKey")) {
        const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
        if (apiKey && bridge.isRunning) bridge.setConfig(apiKey).catch(() => {});
      }
    })
  );

  // ── Periodic status refresh ──────────────────────────────
  refreshStatusBar();
  const interval = setInterval(refreshStatusBar, 30000);
  context.subscriptions.push({ dispose: () => clearInterval(interval) });
}

// ═══════════════════════════════════════════════════════════
// Chat Panel (editor tab)
// ═══════════════════════════════════════════════════════════

function createChatPanel(extensionUri: vscode.Uri) {
  // If panel already exists, reveal it
  if (chatPanel) {
    chatPanel.reveal(vscode.ViewColumn.Active);
    return;
  }

  chatPanel = vscode.window.createWebviewPanel(
    "memorydog.chat",
    "MemoryDog: Chat",
    vscode.ViewColumn.Active,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
    }
  );

  chatPanel.webview.html = readWebviewFile(extensionUri, chatPanel.webview, "chat.html");

  // Send sprite config so the StatusComponent can render the dog
  const spriteUri = chatPanel.webview.asWebviewUri(
    vscode.Uri.joinPath(extensionUri, DOG_SPRITE_SHEET)
  );
  chatPanel.webview.postMessage({
    type: "sprite_config",
    spriteUrl: spriteUri.toString(),
    frameWidth: SPRITE.frameWidth,
    frameHeight: SPRITE.frameHeight,
    columns: SPRITE.columns,
    rows: SPRITE.rows,
    states: DOG_STATES,
    durations: FRAME_DURATIONS,
  });

  chatPanel.webview.onDidReceiveMessage(async (msg) => {
    switch (msg.type) {
      case "ready":
        if (!bridge.isRunning) {
          chatPanel!.webview.postMessage({ type: "setup" });
        } else {
          const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
          if (!apiKey) {
            chatPanel!.webview.postMessage({ type: "setup" });
          } else {
            chatPanel!.webview.postMessage({ type: "ready" });
          }
        }
        break;

      case "chat":
        await handleChat(msg.text);
        break;

      case "setConfig":
        // Validate API key first
        const apiKey = (msg.apiKey || "").trim();
        if (!apiKey) {
          sendToChat({ type: "setup_error", text: "Please enter an API key." });
          return;
        }
        if (apiKey.length < 8) {
          sendToChat({ type: "setup_error", text: "API key is too short. Check your provider key." });
          return;
        }

        // Save config
        await vscode.workspace.getConfiguration("memorydog").update("apiKey", apiKey, vscode.ConfigurationTarget.Global);
        if (msg.model) {
          await vscode.workspace.getConfiguration("memorydog").update("model", msg.model, vscode.ConfigurationTarget.Global);
        }

        // Start bridge
        try { await bridge.setConfig(apiKey, msg.model); } catch {}
        if (!bridge.isRunning) {
          try {
            await bridge.start();
            await bridge.setConfig(apiKey, msg.model);
          } catch (e: any) {
            sendToChat({ type: "setup_error", text: `Failed to start bridge: ${e.message}. Check the MemoryDog Bridge output panel.` });
            return;
          }
        }

        // Skip health check if API key is missing or obviously invalid
        // (health check does provider validation which requires a real key)
        if (apiKey.startsWith("sk-") || apiKey.startsWith("op-")) {
          try {
            const health = await bridge.checkHealth();
            sendToChat({ type: "health", ...health });
          } catch {}
        }

        sendToChat({ type: "ready" });
        refreshStatusBar();
        break;
    }
  });

  chatPanel.onDidDispose(() => {
    chatPanel = undefined;
  });
}

async function handleChat(text: string) {
  if (!chatPanel) return;

  // Validate API key before attempting anything
  const configuredKey = (vscode.workspace.getConfiguration("memorydog").get("apiKey") as string || "").trim();
  if (!configuredKey) {
    sendToChat({ type: "setup_error", text: "Please enter an API key before chatting." });
    return;
  }

  if (!bridge.isRunning) {
    try {
      await bridge.start();
      const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
      if (apiKey) await bridge.setConfig(apiKey);
    } catch (e: any) {
      chatPanel.webview.postMessage({
        type: "error",
        text: `Bridge failed to start: ${e.message}. Check the MemoryDog Bridge output panel.`,
      });
      return;
    }
  }

  const workspace = getWorkspaceName();

  try {
    const response = await bridge.chat(
      text,
      workspace,
      // onStatus — forwards to webview as status messages for StatusComponent
      (statusMsg: string) => {
        chatPanel!.webview.postMessage({ type: "status", text: statusMsg });
      },
      // onToken
      (token: string) => {
        chatPanel!.webview.postMessage({ type: "token", token });
      },
      // onMemories
      (memories: any[]) => {
        chatPanel!.webview.postMessage({ type: "memories_retrieved", memories });
        lastRetrievedMemoryIds = memories.map((m: any) => m.id).filter(Boolean);
      }
    );

    chatPanel.webview.postMessage({ type: "response", content: response });
    refreshStatusBar();
  } catch (e: any) {
    chatPanel.webview.postMessage({ type: "error", text: `Error: ${e.message}` });
  }
}

// ═══════════════════════════════════════════════════════════
// Quick Actions
// ═══════════════════════════════════════════════════════════

async function showQuickActions() {
  const choice = await vscode.window.showQuickPick(
    [
      { label: "$(comment-discussion) Chat", detail: "Open the MemoryDog chat", action: "chat" },
      { label: "$(database) Memory Browser", detail: "Browse persistent memories", action: "memory" },
      { label: "$(zap) Instincts", detail: "View loaded instincts", action: "instincts" },
      { label: "$(settings-gear) Configure", detail: "Set API key and model", action: "config" },
    ],
    { placeHolder: "🐕 MemoryDog — what would you like to do?" }
  );
  if (!choice) return;
  switch (choice.action) {
    case "chat": vscode.commands.executeCommand("memorydog.openChat"); break;
    case "memory": vscode.commands.executeCommand("memorydog.memoryPanel.focus"); break;
    case "instincts": vscode.commands.executeCommand("memorydog.instinctPanel.focus"); break;
    case "config": vscode.commands.executeCommand("memorydog.configure"); break;
  }
}

async function configureApiKey() {
  const apiKey = await vscode.window.showInputBox({
    prompt: "Enter your API key",
    password: true,
    placeHolder: "sk-...",
    value: vscode.workspace.getConfiguration("memorydog").get("apiKey") || "",
  });
  if (apiKey !== undefined) {
    await vscode.workspace.getConfiguration("memorydog").update("apiKey", apiKey, vscode.ConfigurationTarget.Global);
    try {
      await bridge.setConfig(apiKey);
      vscode.window.showInformationMessage("🐕 API key saved!");
    } catch {
      vscode.window.showInformationMessage("🐕 API key saved (restart bridge to apply)");
    }
  }
}

// ═══════════════════════════════════════════════════════════
// Sidebar: Memory Panel
// ═══════════════════════════════════════════════════════════

class MemoryPanelProvider implements vscode.WebviewViewProvider {
  constructor(private readonly extensionUri: vscode.Uri, private readonly bridge: MemoryDogBridge) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = readWebviewFile(this.extensionUri, webviewView.webview, "memory.html");
    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (msg.type === "filter") await this.loadMemories(webviewView, msg.workspace || getWorkspaceName(), msg.workspace || undefined);
    });
    setTimeout(() => this.loadMemories(webviewView, getWorkspaceName()), 500);
  }

  private async loadMemories(webviewView: vscode.WebviewView, workspace: string, query?: string) {
    if (!bridge.isRunning) {
      webviewView.webview.postMessage({ type: "status", text: "Starting bridge…" });
      try {
        await bridge.start();
        const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
        if (apiKey) await bridge.setConfig(apiKey);
        refreshStatusBar();
      } catch (e: any) {
        webviewView.webview.postMessage({ type: "status", text: `Bridge not running: ${e.message}. Open Chat to configure.` });
        return;
      }
    }
    try {
      const result = await bridge.getMemories(workspace, query);
      if (result.error) { webviewView.webview.postMessage({ type: "status", text: result.error }); return; }
      webviewView.webview.postMessage({
        type: "memories", workspace, memories: result.memories || [], total: result.total, highlighted: lastRetrievedMemoryIds,
      });
    } catch (e: any) {
      webviewView.webview.postMessage({ type: "status", text: `Error: ${e.message}` });
    }
  }
}

// ═══════════════════════════════════════════════════════════
// Sidebar: Instinct Panel
// ═══════════════════════════════════════════════════════════

class InstinctPanelProvider implements vscode.WebviewViewProvider {
  constructor(private readonly extensionUri: vscode.Uri, private readonly bridge: MemoryDogBridge) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = readWebviewFile(this.extensionUri, webviewView.webview, "instinct.html");
    setTimeout(() => this.loadInstincts(webviewView), 500);
  }

  private async loadInstincts(webviewView: vscode.WebviewView) {
    if (!bridge.isRunning) {
      webviewView.webview.postMessage({ type: "status", text: "Starting bridge…" });
      try {
        await bridge.start();
        const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
        if (apiKey) await bridge.setConfig(apiKey);
        refreshStatusBar();
      } catch (e: any) {
        webviewView.webview.postMessage({ type: "status", text: `Bridge not running: ${e.message}` });
        return;
      }
    }
    try {
      const result = await bridge.getInstincts();
      if (result.error) { webviewView.webview.postMessage({ type: "status", text: result.error }); return; }
      const instincts = (result.instincts || []).map((i: any) => ({
        name: i.name, description: i.description, prompt: i.prompt || "",
        condition: (i.triggers || []).join(", "), priority: 0.5, active: false,
      }));
      webviewView.webview.postMessage({ type: "instincts", instincts });
    } catch (e: any) {
      webviewView.webview.postMessage({ type: "status", text: `Error: ${e.message}` });
    }
  }
}

// ═══════════════════════════════════════════════════════════
// Shared helpers
// ═══════════════════════════════════════════════════════════

async function startBridgeAsync() {
  try {
    await bridge.start();
    const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
    if (apiKey) await bridge.setConfig(apiKey);
    refreshStatusBar();
  } catch (e) {
    console.error("Failed to start MemoryDog bridge:", e);
  }
}

async function refreshStatusBar() {
  if (!bridge.isRunning) {
    statusBarItem.text = "$(paw) MemoryDog";
    statusBarItem.tooltip = "MemoryDog — bridge not running";
    return;
  }
  try {
    const status = await bridge.getStatus(getWorkspaceName());
    const parts = ["$(paw)"];
    if (status.memory_count > 0) parts.push(`${status.memory_count} memories`);
    if (status.instinct_count > 0) parts.push(`${status.instinct_count} instincts`);
    statusBarItem.text = parts.join(" ");
    statusBarItem.tooltip = `MemoryDog\nWorkspace: ${status.workspace}\nModel: ${status.model}\nProvider: ${status.provider}`;
  } catch {
    statusBarItem.text = "$(paw) MemoryDog";
  }
}

function getWorkspaceName(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) return path.basename(folders[0].uri.fsPath);
  return ".";
}

export function deactivate() {
  bridge?.stop();
}

function readWebviewFile(extensionUri: vscode.Uri, webview: vscode.Webview, filename: string): string {
  const filePath = vscode.Uri.joinPath(extensionUri, "src", "webview", filename);
  let content = fs.readFileSync(filePath.fsPath, "utf-8");
  const nonce = getNonce();
  content = content.replace(
    "<head>",
    `<head>\n<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${webview.cspSource}; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">`
  );
  content = content.replace(/<script>/g, `<script nonce="${nonce}">`);
  return content;
}

function getNonce(): string {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) text += possible.charAt(Math.floor(Math.random() * possible.length));
  return text;
}
