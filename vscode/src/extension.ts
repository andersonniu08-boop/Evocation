import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  const startCmd = vscode.commands.registerCommand("memorydog.start", () => {
    const terminal = vscode.window.createTerminal("MemoryDog");
    terminal.show();
    terminal.sendText("dog chat");
  });

  const memoryProvider = new MemoryPanelProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "memorydog.memoryPanel",
      memoryProvider
    )
  );

  const instinctProvider = new InstinctPanelProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "memorydog.instinctPanel",
      instinctProvider
    )
  );

  context.subscriptions.push(startCmd);
}
// eslint-disable-next-line @typescript-eslint/no-empty-function
export function deactivate() {}

class MemoryPanelProvider implements vscode.WebviewViewProvider {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  constructor(private readonly _extensionUri: vscode.Uri) {}

  public resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = {
      enableScripts: true,
    };
    webviewView.webview.html = this.getHtml();
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
<html><body>
  <h3>🐕 Memory Browser</h3>
  <div id="memories"><em>Agent not started yet.</em></div>
</body></html>`;
  }
}

class InstinctPanelProvider implements vscode.WebviewViewProvider {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  constructor(private readonly _extensionUri: vscode.Uri) {}

  public resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = {
      enableScripts: true,
    };
    webviewView.webview.html = this.getHtml();
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
<html><body>
  <h3>⚡ Instincts</h3>
  <div id="instincts"><em>No instincts loaded.</em></div>
</body></html>`;
  }
}
