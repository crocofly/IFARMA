"""
services/llm/base.py — Абстрактный LLM-клиент.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMClient(ABC):
    """Базовый интерфейс для всех LLM-клиентов."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        images: Optional[list[bytes]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Генерация текста по промпту."""
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        """Получение embedding-вектора."""
        raise NotImplementedError("Embeddings not supported by this client.")

    def with_model(self, model: str) -> "LLMClient":
        """Возвращает клиент с другой моделью (для смены tier)."""
        raise NotImplementedError
