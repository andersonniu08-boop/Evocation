"""Textual application bootstrap."""

from textual.app import App

from cli.ui.chat import ChatScreen
from core.provider import BaseProvider


class EvocationApp(App):
    """Evocation — minimal, single-column TUI."""

    CSS = """
    #conversation {
        height: 1fr;
        border: none;
        padding: 1 2;
    }
    #streaming-line {
        height: auto;
        min-height: 1;
        padding: 0 2;
    }
    #status-indicator {
        height: 1;
        dock: bottom;
        padding: 0 2;
    }
    #user-input {
        dock: bottom;
        margin: 1 2;
    }
    """

    def __init__(
        self,
        workspace: str = ".",
        provider: BaseProvider | None = None,
        model_name: str = "mock",
    ):
        super().__init__()
        self.workspace = workspace
        self.provider = provider
        self.model_name = model_name

    def on_mount(self):
        self.push_screen(
            ChatScreen(
                workspace=self.workspace,
                provider=self.provider,
                model_name=self.model_name,
            )
        )
