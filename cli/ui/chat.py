"""Chat screen — clean single-column, transient status, smooth streaming."""

import os
import time

from textual.screen import Screen
from textual.widgets import Input, RichLog, Static

from core.provider import BaseProvider, MockProvider


class ChatScreen(Screen):
    """Single-column chat with transient status indicator."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
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
        self.state = None
        self.total_tokens = 0

    def compose(self):
        yield RichLog(id="conversation", highlight=True, markup=True, wrap=True)
        yield Static(id="streaming-line")
        yield Static(id="status-indicator")
        yield Input(placeholder="> ", id="user-input")

    async def on_mount(self):
        from core.agent_loop import init_agent

        try:
            self.state = await init_agent(self.workspace)
        except Exception:
            self.state = None

        conv = self.query_one("#conversation", RichLog)
        conv.write("[dim]Evocation ready[/]")

        if self.state and self.state.workspace:
            try:
                from core.memory import count_memories

                count = await count_memories(self.state.workspace)
                if count > 0:
                    conv.write(f"[dim]{count} memories from previous sessions[/]")
            except Exception:
                pass

        self._update_status()
        self.query_one("#user-input", Input).focus()
        self._start_time = time.time()

    async def on_input_submitted(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        event.input.disabled = True

        conv = self.query_one("#conversation", RichLog)
        indicator = self.query_one("#status-indicator", Static)
        stream = self.query_one("#streaming-line", Static)

        conv.write(f"\n[bold]You:[/] {text}")
        conv.scroll_end()

        if self.state is None:
            from core.agent_loop import AgentState

            self.provider = self.provider or MockProvider()
            ws = os.path.basename(os.path.abspath(self.workspace)) or self.workspace
            self.state = AgentState(workspace=ws)
            response = self.provider.chat([])
            conv.write(f"[bold]Evocation:[/] {response.content}")
            event.input.disabled = False
            event.input.focus()
            return

        from core.agent_loop import run_turn

        # Status updates go to transient indicator, NOT conversation
        def on_status(msg: str):
            indicator.update(f"[dim]{msg}[/]")

        indicator.update("[dim]Thinking...[/]")
        stream.update("")

        # Stream tokens into the streaming-line Static widget
        response_parts = []

        def on_token(token: str):
            response_parts.append(token)
            full = "".join(response_parts)
            stream.update(f"[bold]Evocation:[/] {full}")

        response_text = await run_turn(
            self.provider,
            self.state,
            text,
            on_status=on_status,
            on_token=on_token,
        )

        # Move response to conversation history, clear streaming
        indicator.update("")
        stream.update("")
        conv.write(f"[bold]Evocation:[/] {response_text}")

        self.total_tokens += self.provider.last_tokens
        self._update_status()

        conv.scroll_end()
        event.input.disabled = False
        event.input.focus()

    def _update_status(self):
        indicator = self.query_one("#status-indicator", Static)
        parts = []
        if self.model_name:
            parts.append(f"model: {self.model_name}")
        if self.total_tokens:
            parts.append(f"{self.total_tokens} tokens")
        parts.append(f"{self.workspace}")
        indicator.update("[dim]" + " | ".join(parts) + "[/]")

    def action_focus_input(self):
        self.query_one("#user-input", Input).focus()
