"""Chat screen — conversation pane, input, status bar."""
import os

from textual.screen import Screen
from textual.widgets import Header, Input, RichLog

from cli.ui.widgets import StatusBar
from core.provider import BaseProvider, MockProvider


class ChatScreen(Screen):
    """Main chat interface."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+s", "focus_input", "Focus Input"),
    ]

    def __init__(
        self,
        workspace: str = ".",
        provider: BaseProvider | None = None,
        model_name: str = "mock",
    ):
        super().__init__()
        self.workspace = workspace
        self.provider = provider or MockProvider()
        self.model_name = model_name
        self.state = None  # set in on_mount
        self.total_tokens = 0
        ws_name = os.path.basename(os.path.abspath(workspace)) or workspace
        self.status = StatusBar()
        self.status.workspace = ws_name
        self.status.model = model_name

    def compose(self):
        yield Header(show_clock=True)
        yield RichLog(id="conversation", highlight=True, markup=True, wrap=True)
        yield self.status
        yield Input(placeholder="> Type your message...", id="user-input")

    async def on_mount(self):
        from core.agent_loop import init_agent

        try:
            self.state = await init_agent(self.workspace)
        except Exception:
            self.state = None

        conv = self.query_one("#conversation", RichLog)
        conv.write("[bold blue]🐕 MemoryDog ready.[/]")
        self._show_status(conv)

        self.query_one("#user-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        event.input.disabled = True

        conv = self.query_one("#conversation", RichLog)
        conv.write(f"[bold blue]You:[/] {text}")

        if self.state is None:
            from core.agent_loop import AgentState
            from core.provider import MockProvider

            self.provider = self.provider or MockProvider()
            ws = os.path.basename(os.path.abspath(self.workspace)) or self.workspace
            self.state = AgentState(workspace=ws)
            response = self.provider.chat([])
            conv.write(f"[bold green]MemoryDog:[/] {response.content}")
            event.input.disabled = False
            event.input.focus()
            return

        from core.agent_loop import pop_status, run_turn

        response_text = await run_turn(self.provider, self.state, text)

        for msg in pop_status():
            conv.write(f"[dim]🐕 {msg}[/]")

        conv.write(f"[bold green]MemoryDog:[/] {response_text}")

        self.total_tokens += self.provider.last_tokens
        await self._refresh_memory_counts()
        conv.scroll_end()
        event.input.disabled = False
        event.input.focus()

    def _show_status(self, conv: RichLog):
        if self.state and self.state.active_instincts:
            names = ", ".join(self.state.active_instincts)
            conv.write(f"[dim]🐕 Instincts active: {names}[/]")
        conv.write(f"[dim]🐕 Model: {self.model_name}[/]")

    async def _refresh_memory_counts(self):
        try:
            from core.memory import count_instinct_activations, count_memories

            self.status.memory_count = await count_memories(self.state.workspace)
            self.status.instinct_count = await count_instinct_activations()
        except Exception:
            pass

    def action_focus_input(self):
        self.query_one("#user-input", Input).focus()
