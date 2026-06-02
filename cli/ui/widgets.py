"""Custom widgets for MemoryDog TUI."""
from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Static):
    """Bottom status bar showing agent state."""

    workspace: reactive[str] = reactive("")
    memory_count: reactive[int] = reactive(0)
    instinct_count: reactive[int] = reactive(0)
    session_time: reactive[str] = reactive("0m")
    model: reactive[str] = reactive("mock")

    def on_mount(self):
        self.border_title = self._build_text()

    def watch_workspace(self, value: str):
        self.border_title = self._build_text()

    def watch_memory_count(self, value: int):
        self.border_title = self._build_text()

    def _build_text(self) -> str:
        return (
            f"\U0001F415 Ready  "
            f"|  \u25a1 {self.workspace}  "
            f"|  {self.memory_count} memories  "
            f"|  {self.instinct_count} instincts  "
            f"|  {self.session_time}  "
            f"|  {self.model}"
        )


class DogMessage(Static):
    """Dog status message in chrome."""

    def __init__(self, text: str):
        super().__init__()
        self.update(f"\U0001F415 {text}")
