"""Chat screen — conversation pane, input, status bar."""
import os

from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Input, Static

from cli.ui.widgets import StatusBar
from core.agent_loop import AgentState, run_turn
from core.provider import MockProvider


class ChatScreen(Screen):
    """Main chat interface."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "focus_input", "Focus Input"),
    ]

    def __init__(self, workspace: str = "."):
        super().__init__()
        self.workspace = workspace
        self.provider = MockProvider()
        self.state = AgentState(workspace=workspace)
        ws_name = os.path.basename(os.path.abspath(workspace)) or workspace
        self.status = StatusBar()
        self.status.workspace = ws_name

    def compose(self):
        yield Header(show_clock=True)
        yield VerticalScroll(id="conversation")
        yield self.status
        yield Input(placeholder="> Type your message...", id="user-input")

    def on_mount(self):
        self.query_one("#user-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(Static(f"[bold blue]You:[/] {text}"))

        self.status.model = "mock (LiteLLM pending)"
        response_text = run_turn(self.provider, self.state, text)
        conv.mount(Static(f"[bold green]MemoryDog:[/] {response_text}"))

        conv.scroll_end()

    def action_focus_input(self):
        self.query_one("#user-input", Input).focus()
