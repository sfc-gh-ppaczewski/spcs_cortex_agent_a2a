"""
A2A client for calling the Snowflake Cortex A2A agent (SPCS-to-SPCS).
"""
import os
import uuid
import json

import httpx
from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    SendMessageSuccessResponse,
    Task,
    TaskState,
    GetTaskRequest,
    TaskQueryParams,
    GetTaskSuccessResponse,
    Message,
)


class SnowflakeA2AClient:
    """Sends queries to the Snowflake Cortex A2A agent via A2A protocol."""

    def __init__(self):
        self.agent_url = os.getenv(
            "SNOWFLAKE_A2A_AGENT_URL", "http://cortex-a2a-agent:8000"
        )
        print(f"Snowflake A2A client target: {self.agent_url}")

    async def send_query(self, text: str) -> str:
        """Send a text query to the Snowflake A2A agent and return the response.

        Args:
            text: The query text to send.

        Returns:
            The agent's text response, or an error message.
        """
        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": text}],
                "messageId": uuid.uuid4().hex,
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as httpx_client:
            client = A2AClient(httpx_client=httpx_client, url=self.agent_url)

            request = SendMessageRequest(
                id=str(uuid.uuid4()),
                params=MessageSendParams(**payload),
            )

            response = await client.send_message(request)

            # Handle direct message response
            if hasattr(response, "root"):
                result = response.root
                if isinstance(result, SendMessageSuccessResponse):
                    return self._extract_text(result.result)

            # Fallback: try to extract from raw response
            raw = response.model_dump(mode="json", exclude_none=True)
            return self._extract_text_from_dict(raw)

    def _extract_text(self, result) -> str:
        """Extract text from an A2A result object (Task or Message)."""
        # If result is a Message with parts
        if isinstance(result, Message):
            return self._text_from_parts(result.parts)

        # If result is a Task, look at the status message or artifacts
        if isinstance(result, Task):
            if result.status and result.status.message:
                return self._text_from_parts(result.status.message.parts)
            if result.artifacts:
                for artifact in result.artifacts:
                    if artifact.parts:
                        text = self._text_from_parts(artifact.parts)
                        if text:
                            return text

        return "No response received from Snowflake agent."

    def _text_from_parts(self, parts) -> str:
        """Extract text from a list of parts."""
        if not parts:
            return ""
        texts = []
        for part in parts:
            actual = getattr(part, "root", part)
            if hasattr(actual, "text"):
                texts.append(actual.text)
        return "\n".join(texts) if texts else ""

    def _extract_text_from_dict(self, data: dict) -> str:
        """Fallback: extract text from a raw JSON dict."""
        result = data.get("result", {})
        if isinstance(result, dict):
            parts = result.get("parts", [])
            for part in parts:
                if part.get("kind") == "text" or part.get("type") == "text":
                    return part.get("text", "")
        return "No response received from Snowflake agent."
