import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { MemoryDogBridge } from "./bridge";

let bridge: MemoryDogBridge;
let statusBarItem: vscode.StatusBarItem;
let chatProvider: ChatViewProvider | undefined;

export function activate(context: vscode.ExtensionContext) {
  // ── Status Bar ──────────────────────────────────────────
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBarItem.text = "$(paw) MemoryDog";
  statusBarItem.tooltip = "MemoryDog — memory-augmented coding agent";
  statusBarItem.command = "memorydog.focusChat";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // ── Bridge ──────────────────────────────────────────────
  bridge = new MemoryDogBridge();

  // Try to start the bridge, but don't block activation
  startBridgeAsync();

  // ── Chat Webview Provider ───────────────────────────────
  chatProvider = new ChatViewProvider(context.extensionUri, bridge);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "memorydog.chatView",
      chatProvider,
      { webviewOptions: { retainContextWhenHidden: true } }
    )
  );

  // ── Memory Panel Provider ───────────────────────────────
  const memoryProvider = new MemoryPanelProvider(context.extensionUri, bridge);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "memorydog.memoryPanel",
      memoryProvider
    )
  );

  // ── Instinct Panel Provider ─────────────────────────────
  const instinctProvider = new InstinctPanelProvider(context.extensionUri, bridge);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "memorydog.instinctPanel",
      instinctProvider
    )
  );

  // ── Dog View Provider ───────────────────────────────────
  const dogProvider = new DogViewProvider(context.extensionUri, bridge);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "memorydog.dogView",
      dogProvider
    )
  );

  // ── Commands ────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand("memorydog.focusChat", () => {
      vscode.commands.executeCommand("memorydog.chatView.focus");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("memorydog.showQuickActions", async () => {
      const choice = await vscode.window.showQuickPick(
        [
          {
            label: "$(comment-discussion) Chat",
            detail: "Start chatting with MemoryDog",
            action: "chat",
          },
          {
            label: "$(database) Memory Browser",
            detail: "Browse persistent memories",
            action: "memory",
          },
          {
            label: "$(zap) Instincts",
            detail: "View loaded instincts",
            action: "instincts",
          },
          {
            label: "$(paw) Mascot",
            detail: "Show the animated dog",
            action: "dog",
          },
          {
            label: "$(settings-gear) Configure",
            detail: "Set API key and model",
            action: "config",
          },
        ],
        { placeHolder: "🐕 MemoryDog — what would you like to do?" }
      );
      if (!choice) { return; }
      const cmd: Record<string, string> = {
        chat: "memorydog.chatView.focus",
        memory: "memorydog.memoryPanel.focus",
        instincts: "memorydog.instinctPanel.focus",
        dog: "memorydog.dogView.focus",
        config: "memorydog.configure",
      };
      vscode.commands.executeCommand(cmd[choice.action]);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("memorydog.configure", async () => {
      const apiKey = await vscode.window.showInputBox({
        prompt: "Enter your API key",
        password: true,
        placeHolder: "sk-...",
        value: vscode.workspace.getConfiguration("memorydog").get("apiKey") || "",
      });
      if (apiKey !== undefined) {
        await vscode.workspace.getConfiguration("memorydog").update(
          "apiKey",
          apiKey,
          vscode.ConfigurationTarget.Global
        );
        // Sync to Python config
        try {
          await bridge.setConfig(apiKey);
          vscode.window.showInformationMessage("🐕 API key saved!");
        } catch {
          // Bridge might not be running yet
          vscode.window.showInformationMessage("🐕 API key saved (restart bridge to apply)");
        }
      }
    })
  );

  // Legacy commands for compatibility
  context.subscriptions.push(
    vscode.commands.registerCommand("memorydog.start", () =>
      vscode.commands.executeCommand("memorydog.chatView.focus")
    ),
    vscode.commands.registerCommand("memorydog.startChat", () =>
      vscode.commands.executeCommand("memorydog.chatView.focus")
    ),
    vscode.commands.registerCommand("memorydog.showMemoryPanel", () =>
      vscode.commands.executeCommand("memorydog.memoryPanel.focus")
    ),
    vscode.commands.registerCommand("memorydog.showInstinctPanel", () =>
      vscode.commands.executeCommand("memorydog.instinctPanel.focus")
    ),
    vscode.commands.registerCommand("memorydog.showDogView", () =>
      vscode.commands.executeCommand("memorydog.dogView.focus")
    )
  );

  // ── Configuration change listener ───────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("memorydog.apiKey")) {
        const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
        if (apiKey && bridge.isRunning) {
          bridge.setConfig(apiKey).catch(() => {});
        }
      }
    })
  );

  // ── Refresh status periodically ─────────────────────────
  refreshStatusBar();
  const interval = setInterval(refreshStatusBar, 30000);
  context.subscriptions.push({ dispose: () => clearInterval(interval) });
}

async function startBridgeAsync() {
  try {
    await bridge.start();

    // Sync VS Code settings to Python config
    const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
    if (apiKey) {
      await bridge.setConfig(apiKey);
    }

    refreshStatusBar();

    // Notify chat provider that bridge is ready
    chatProvider?.onBridgeReady();
  } catch (e) {
    console.error("Failed to start MemoryDog bridge:", e);
    // Bridge will be retried when user sends first message
  }
}

async function refreshStatusBar() {
  if (!bridge.isRunning) {
    statusBarItem.text = "$(paw) MemoryDog";
    statusBarItem.tooltip = "MemoryDog — bridge not running";
    return;
  }

  try {
    const workspace = getWorkspaceName();
    const status = await bridge.getStatus(workspace);
    const parts = ["$(paw)"];
    if (status.memory_count > 0) {
      parts.push(`${status.memory_count} memories`);
    }
    if (status.instinct_count > 0) {
      parts.push(`${status.instinct_count} instincts`);
    }
    statusBarItem.text = parts.join(" ");
    statusBarItem.tooltip = `MemoryDog\nWorkspace: ${status.workspace}\nModel: ${status.model}\nProvider: ${status.provider}`;
  } catch {
    statusBarItem.text = "$(paw) MemoryDog";
  }
}

function getWorkspaceName(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return path.basename(folders[0].uri.fsPath);
  }
  return ".";
}

export function deactivate() {
  bridge?.stop();
}

// ── Helper: read webview HTML files ───────────────────────
function readWebviewFile(
  extensionUri: vscode.Uri,
  webview: vscode.Webview,
  filename: string
): string {
  const filePath = vscode.Uri.joinPath(extensionUri, "src", "webview", filename);
  let content = fs.readFileSync(filePath.fsPath, "utf-8");

  // Inject webview resource URIs for CSP
  const nonce = getNonce();
  content = content.replace(
    "<head>",
    `<head>\n<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">`
  );
  content = content.replace(/<script>/g, `<script nonce="${nonce}">`);
  return content;
}

function getNonce(): string {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}

// ═══════════════════════════════════════════════════════════
// ChatViewProvider
// ═══════════════════════════════════════════════════════════

class ChatViewProvider implements vscode.WebviewViewProvider {
  private view: vscode.WebviewView | undefined;
  private pendingFirstMessage: string | undefined;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly bridge: MemoryDogBridge
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = readWebviewFile(
      this.extensionUri,
      webviewView.webview,
      "chat.html"
    );

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      switch (msg.type) {
        case "ready":
          // Check if bridge is running, if not show setup
          if (!this.bridge.isRunning) {
            webviewView.webview.postMessage({
              type: "setup",
            });
          } else {
            // Check for API key
            const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
            if (!apiKey) {
              webviewView.webview.postMessage({ type: "setup" });
            } else {
              webviewView.webview.postMessage({ type: "ready" });
            }
          }
          break;

        case "chat":
          await this.handleChat(msg.text, webviewView);
          break;

        case "setConfig":
          if (msg.apiKey) {
            await vscode.workspace.getConfiguration("memorydog").update(
              "apiKey",
              msg.apiKey,
              vscode.ConfigurationTarget.Global
            );
          }
          if (msg.model) {
            await vscode.workspace.getConfiguration("memorydog").update(
              "model",
              msg.model,
              vscode.ConfigurationTarget.Global
            );
          }
          // Sync to Python config and restart bridge if needed
          try {
            await this.bridge.setConfig(msg.apiKey, msg.model);
          } catch {
            // Bridge might not be running
          }
          if (!this.bridge.isRunning) {
            try {
              await this.bridge.start();
              if (msg.apiKey) {
                await this.bridge.setConfig(msg.apiKey, msg.model);
              }
            } catch (e: any) {
              webviewView.webview.postMessage({
                type: "error",
                text: `Failed to start: ${e.message}`,
              });
              return;
            }
          }
          webviewView.webview.postMessage({ type: "ready" });
          refreshStatusBar();
          break;
      }
    });

    // If bridge becomes ready later, notify
    if (this.bridge.isRunning) {
      webviewView.webview.postMessage({ type: "ready" });
    }
  }

  onBridgeReady() {
    if (this.view) {
      this.view.webview.postMessage({ type: "ready" });
    }
  }

  private async handleChat(text: string, webviewView: vscode.WebviewView) {
    // Ensure bridge is running
    if (!this.bridge.isRunning) {
      try {
        await this.bridge.start();
        const apiKey = vscode.workspace.getConfiguration("memorydog").get("apiKey") as string;
        if (apiKey) {
          await this.bridge.setConfig(apiKey);
        }
      } catch (e: any) {
        webviewView.webview.postMessage({
          type: "error",
          text: `Bridge failed to start: ${e.message}. Make sure MemoryDog is installed (\`pip install -e .\` from the repo).`,
        });
        return;
      }
    }

    const workspace = getWorkspaceName();

    // Update dog to sniffing
    notifyDog("sniffing");

    try {
      const response = await this.bridge.chat(
        text,
        workspace,
        (statusMsg: string) => {
          webviewView.webview.postMessage({ type: "status", text: statusMsg });
          // Map status to dog state
          if (statusMsg.toLowerCase().includes("fetching") || statusMsg.toLowerCase().includes("sniffing")) {
            notifyDog("sniffing");
          } else if (statusMsg.toLowerCase().includes("found") || statusMsg.toLowerCase().includes("learned")) {
            notifyDog("excited");
          } else if (statusMsg.toLowerCase().includes("thinking") || statusMsg.toLowerCase().includes("executing") || statusMsg.toLowerCase().includes("running")) {
            notifyDog("sniffing");
          }
        },
        (token: string) => {
          webviewView.webview.postMessage({ type: "token", token });
        }
      );

      webviewView.webview.postMessage({ type: "response", content: response });
      notifyDog("idle");
      refreshStatusBar();
    } catch (e: any) {
      webviewView.webview.postMessage({
        type: "error",
        text: `Error: ${e.message}`,
      });
      notifyDog("idle");
    }
  }
}

// ═══════════════════════════════════════════════════════════
// MemoryPanelProvider
// ═══════════════════════════════════════════════════════════

class MemoryPanelProvider implements vscode.WebviewViewProvider {
  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly bridge: MemoryDogBridge
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = readWebviewFile(
      this.extensionUri,
      webviewView.webview,
      "memory.html"
    );

    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (msg.type === "filter") {
        const workspace = msg.workspace || getWorkspaceName();
        await this.loadMemories(webviewView, workspace, msg.workspace || undefined);
      }
    });

    // Load initial data
    setTimeout(() => this.loadMemories(webviewView, getWorkspaceName()), 500);
  }

  private async loadMemories(
    webviewView: vscode.WebviewView,
    workspace: string,
    query?: string
  ) {
    if (!this.bridge.isRunning) {
      webviewView.webview.postMessage({
        type: "status",
        text: "Bridge not running. Open the Chat panel to start MemoryDog.",
      });
      return;
    }

    try {
      const result = await this.bridge.getMemories(workspace, query);
      if (result.error) {
        webviewView.webview.postMessage({
          type: "status",
          text: result.error,
        });
        return;
      }

      webviewView.webview.postMessage({
        type: "memories",
        workspace,
        memories: result.memories || [],
        total: result.total,
      });
    } catch (e: any) {
      webviewView.webview.postMessage({
        type: "status",
        text: `Error: ${e.message}`,
      });
    }
  }
}

// ═══════════════════════════════════════════════════════════
// InstinctPanelProvider
// ═══════════════════════════════════════════════════════════

class InstinctPanelProvider implements vscode.WebviewViewProvider {
  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly bridge: MemoryDogBridge
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = { enableScripts: true };

    const html = readWebviewFile(this.extensionUri, webviewView.webview, "instinct.html");
    webviewView.webview.html = html;

    // Load initial data
    setTimeout(() => this.loadInstincts(webviewView), 500);
  }

  private async loadInstincts(webviewView: vscode.WebviewView) {
    if (!this.bridge.isRunning) {
      webviewView.webview.postMessage({
        type: "status",
        text: "Bridge not running. Open the Chat panel to start MemoryDog.",
      });
      return;
    }

    try {
      const result = await this.bridge.getInstincts();
      if (result.error) {
        webviewView.webview.postMessage({
          type: "status",
          text: result.error,
        });
        return;
      }

      // Map to the format the HTML expects
      const instincts = (result.instincts || []).map((i: any) => ({
        name: i.name,
        description: i.description,
        prompt: i.prompt || "",
        condition: (i.triggers || []).join(", "),
        priority: 0.5,
        active: false,
      }));

      webviewView.webview.postMessage({
        type: "instincts",
        instincts,
      });
    } catch (e: any) {
      webviewView.webview.postMessage({
        type: "status",
        text: `Error: ${e.message}`,
      });
    }
  }
}

// ═══════════════════════════════════════════════════════════
// DogViewProvider
// ═══════════════════════════════════════════════════════════

let dogState: string = "idle";

function notifyDog(state: string) {
  dogState = state;
  // State is read by the dog webview when it polls or we could
  // push via postMessage if we had a reference to the provider.
  // For now, the dog panel queries state from the bridge.
}

class DogViewProvider implements vscode.WebviewViewProvider {
  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly bridge: MemoryDogBridge
  ) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = readWebviewFile(
      this.extensionUri,
      webviewView.webview,
      "dog.html"
    );

    webviewView.webview.onDidReceiveMessage((msg) => {
      if (msg.type === "setState") {
        dogState = msg.state;
      }
    });

    // Poll dog state from the bridge
    const interval = setInterval(() => {
      if (this.bridge.isRunning) {
        webviewView.webview.postMessage({
          type: "state",
          state: dogState,
        });
      } else {
        webviewView.webview.postMessage({
          type: "state",
          state: "sleeping",
        });
      }
    }, 500);

    webviewView.onDidDispose(() => clearInterval(interval));

    setTimeout(() => {
      webviewView.webview.postMessage({
        type: "state",
        state: this.bridge.isRunning ? "idle" : "sleeping",
      });
    }, 300);
  }
}
