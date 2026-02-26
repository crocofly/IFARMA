"""
services/llm/groq_client.py — Groq LLM-клиент.
"""

import asyncio
from typing import Optional

from app.services.llm.base import LLMClient


class GroqLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.api_key = api_key
        self.model = model

        from openai import OpenAI
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

    async def generate(
        self,
        prompt: str,
        images: Optional[list[bytes]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        def _call() -> str:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
            )
            return (resp.choices[0].message.content or "").strip()

        return await asyncio.to_thread(_call)

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Groq does not support embeddings.")

    def with_model(self, model: str) -> "GroqLLMClient":
        return GroqLLMClient(api_key=self.api_key, model=model)
