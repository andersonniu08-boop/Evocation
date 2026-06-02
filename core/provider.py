"""LLM provider abstraction."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Message:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    token_count: int = 0


class BaseProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        ...


class MockProvider(BaseProvider):
    def chat(self, messages: list[Message], tools: list[dict] | None = None) -> LLMResponse:
        last = messages[-1].content.lower()
        if "hello" in last or "hi" in last:
            return LLMResponse(content="Hello! I'm MemoryDog. How can I help you today?")
        return LLMResponse(
            content="I understand. Let me help you with that.",
            token_count=42,
        )
