"""
Async LLM client for the local llama.cpp server (OpenAI-compatible API).
"""
import os
from openai import AsyncOpenAI


class LLMClient:
    def __init__(self):
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1")
        model = os.getenv("LLM_MODEL", "local-model")

        self.client = AsyncOpenAI(base_url=base_url, api_key="ignored")
        self.model = model

    async def complete(self, system_prompt: str, user_message: str) -> str:
        """Send a chat completion request to the local LLM."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""
