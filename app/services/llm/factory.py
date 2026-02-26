"""
services/llm/factory.py — Фабрика LLM-клиентов.
"""

from app.config.settings import settings
from app.services.llm.base import LLMClient


def build_llm_client(model_tier: str = "pro") -> LLMClient:
    """
    Создаёт LLM-клиент по настройкам из .env.

    Args:
        model_tier: "pro" (мощная) или "fast" (быстрая)
    """
    provider = settings.LLM_PROVIDER

    if provider == "mock":
        from app.services.llm.mock_client import MockLLMClient
        return MockLLMClient()

    if provider == "gemini":
        from app.services.llm.gemini_client import GeminiLLMClient
        model = settings.GEMINI_MODEL_PRO if model_tier == "pro" else settings.GEMINI_MODEL_FAST
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            model=model,
            embed_model=settings.GEMINI_EMBED_MODEL,
        )

    if provider == "groq":
        from app.services.llm.groq_client import GroqLLMClient
        model = settings.GROQ_MODEL_PRO if model_tier == "pro" else settings.GROQ_MODEL_FAST
        return GroqLLMClient(api_key=settings.GROQ_API_KEY, model=model)

    raise RuntimeError(f"Unknown LLM_PROVIDER: {provider}. Use 'gemini', 'groq', or 'mock'.")