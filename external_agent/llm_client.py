"""
LLM client wrapper using the OpenAI SDK pointed at a local llama.cpp server.
"""
import os
from openai import OpenAI


class LLMClient:
    """Client for the local llama.cpp server (OpenAI-compatible API)."""

    def __init__(self):
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1")
        self.client = OpenAI(base_url=base_url, api_key="not-needed")
        self.model = os.getenv("LLM_MODEL", "local-model")
        print(f"LLM client initialized: {base_url}, model={self.model}")

    def complete(self, system_prompt: str, user_message: str) -> str:
        """Send a chat completion request to the local LLM.

        Args:
            system_prompt: The system instruction for the LLM.
            user_message: The user's message.

        Returns:
            The LLM's text response.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=256,
            temperature=0.1,
        )
        return response.choices[0].message.content or ""
