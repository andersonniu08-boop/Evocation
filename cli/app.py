"""Textual application bootstrap."""
from textual.app import App

from cli.ui.chat import ChatScreen


class MemoryDogApp(App):
    """MemoryDog Textual application."""

    CSS = """
    #conversation {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    #user-input {
        dock: bottom;
        margin: 1 0 0 0;
    }
    StatusBar {
        dock: bottom;
        height: 1;
        background: $panel;
    }
    """

    def __init__(self, workspace: str = "."):
        super().__init__()
        self.workspace = workspace

    def on_mount(self):
        self.push_screen(ChatScreen(workspace=self.workspace))
