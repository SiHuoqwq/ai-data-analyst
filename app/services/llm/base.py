from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLM(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Return {"content": str, "tool_calls": list | None}"""
        ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield content chunks"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
