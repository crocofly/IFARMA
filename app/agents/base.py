from abc import ABC, abstractmethod
from typing import Any, Dict

from app.services.llm.base import LLMClient


class AgentResult:
    def __init__(self, data: Any, sources: list[str] | None = None, extra: dict | None = None):
        self.data = data
        self.sources = sources or []
        self.extra = extra or {}


class BaseAgent(ABC):
    def __init__(self, name: str, llm: LLMClient):
        self.name = name
        self.llm = llm

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        Основная логика агента.
        """
        raise NotImplementedError

    def validate(self, result: AgentResult) -> bool:
        return result.data is not None

    def get_sources(self, result: AgentResult) -> list[str]:
        return result.sources