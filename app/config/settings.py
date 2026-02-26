"""
config/settings.py — Конфигурация приложения.
Переключение провайдера — только через .env, код менять не нужно.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None or val == "":
        raise RuntimeError(f"Missing env var: {name}")
    return val


class Settings:
    # === Провайдер: "gemini" / "groq" / "mock" ===
    LLM_PROVIDER: str = _get_env("LLM_PROVIDER", "mock")

    # === Gemini ===
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL_PRO: str = _get_env("GEMINI_MODEL_PRO", "gemini-2.5-pro")
    GEMINI_MODEL_FAST: str = _get_env("GEMINI_MODEL_FAST", "gemini-2.0-flash")
    GEMINI_EMBED_MODEL: str = _get_env("GEMINI_EMBED_MODEL", "text-embedding-004")

    # === Groq ===
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL_PRO: str = _get_env("GROQ_MODEL_PRO", "llama-3.3-70b-versatile")
    GROQ_MODEL_FAST: str = _get_env("GROQ_MODEL_FAST", "meta-llama/llama-4-scout-17b-16e-instruct")

    # === Database ===
    DATABASE_URL: str = _get_env("DATABASE_URL", "sqlite:///./ifarma.db")

    # === Cache ===
    PK_CACHE_TTL_DAYS: int = int(os.getenv("PK_CACHE_TTL_DAYS", "30"))

    # === Security ===
    JWT_SECRET: str = _get_env("JWT_SECRET", "change-me-in-production")
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


settings = Settings()
