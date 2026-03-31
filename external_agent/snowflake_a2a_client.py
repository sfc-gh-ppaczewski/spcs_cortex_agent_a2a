"""
A2A client for calling the Snowflake Cortex A2A agent (SPCS-to-SPCS).
"""
import os
import re
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

    def __init__(self, url: str = None):
        self.agent_url = url or os.getenv(
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
        raw = "\n".join(texts) if texts else ""
        return self._clean_response(raw)

    @staticmethod
    def _clean_response(text: str) -> str:
        """Remove duplicated content and chain-of-thought from agent responses.

        The Cortex Agent sometimes returns its thinking process followed by the
        real answer, then repeats the whole block.  The structure looks like:

            [CoT reasoning] [formatted answer] [CoT reasoning] [formatted answer]

        Strategy:
        1. Find the largest duplicated block and keep only one copy.
        2. Strip any chain-of-thought lines that precede the real answer.
        """
        if not text:
            return text

        # --- Step 1: Remove duplicate content blocks ---
        # Look for the first markdown heading or other structured-answer marker.
        # The formatted answer typically starts with "## " or "**".  If we find
        # two occurrences, we can locate the duplicate boundary.
        # Try to find duplicate answer blocks by looking for repeated
        # markdown-heading sections.
        heading_pattern = re.compile(r"^##\s+", re.MULTILINE)
        headings = list(heading_pattern.finditer(text))
        if len(headings) >= 2:
            # Group headings by their line text to find where the duplication
            # starts.  The same heading appearing twice means we have a repeat.
            heading_lines = []
            for m in headings:
                # Extract the full line of the heading
                line_end = text.find("\n", m.start())
                if line_end == -1:
                    line_end = len(text)
                heading_lines.append((m.start(), text[m.start():line_end].strip()))

            # Find the first heading text that appears more than once
            seen = {}
            dup_start = None
            for pos, line_text in heading_lines:
                if line_text in seen:
                    dup_start = seen[line_text]  # position of the first occurrence
                    dup_second = pos  # position of the second occurrence
                    break
                seen[line_text] = pos

            if dup_start is not None:
                # The real answer starts at dup_start; the duplicate starts at
                # dup_second.  Keep only dup_start .. dup_second.
                answer_block = text[dup_start:dup_second].strip()
                if len(answer_block) > 50:
                    text = answer_block

        # --- Step 1b: Fallback simple-half deduplication ---
        half = len(text) // 2
        if half > 100:
            first = text[:half].strip()
            second = text[half:].strip()
            if first == second:
                text = first

        # --- Step 2: Strip chain-of-thought preamble ---
        lines = text.split("\n")
        cot_prefixes = (
            "The user is ",
            "I should ",
            "Based on my ",
            "I need to ",
            "Let me ",
            "I have access to:",
            "I can see that ",
            "I have access to two",  # specific to Cortex Agent CoT
        )
        first_content = 0
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            # Numbered list items in CoT preamble (e.g. "1. A Cortex Analyst...")
            if re.match(r"^\d+\.\s+A\s+Cortex\s", stripped_line):
                first_content = i + 1
                continue
            if any(stripped_line.startswith(p) for p in cot_prefixes):
                first_content = i + 1
                continue
            # Stop scanning once we hit a non-CoT, non-empty line
            break

        if first_content > 0:
            while first_content < len(lines) and not lines[first_content].strip():
                first_content += 1
            cleaned = "\n".join(lines[first_content:]).strip()
            if cleaned:
                text = cleaned

        # --- Step 3: Trim trailing CoT fragments ---
        # After dedup, the text may end with the start of another CoT block
        # (e.g. "I have access to two main data sources...") that was left
        # behind after the heading-based cut.
        trailing_cot = (
            "I have access to ",
            "The user is ",
            "I should ",
            "Based on ",
            "I need to ",
            "Let me ",
        )
        lines = text.rstrip().split("\n")
        while lines:
            last = lines[-1].strip()
            if not last:
                lines.pop()
                continue
            if any(last.startswith(p) for p in trailing_cot):
                lines.pop()
                continue
            if re.match(r"^\d+\.\s+A\s+Cortex\s", last):
                lines.pop()
                continue
            break
        text = "\n".join(lines).rstrip()

        return text

    def _extract_text_from_dict(self, data: dict) -> str:
        """Fallback: extract text from a raw JSON dict."""
        result = data.get("result", {})
        if isinstance(result, dict):
            parts = result.get("parts", [])
            for part in parts:
                if part.get("kind") == "text" or part.get("type") == "text":
                    return self._clean_response(part.get("text", ""))
        return "No response received from Snowflake agent."
