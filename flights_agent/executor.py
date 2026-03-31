"""
Executor module for Snowflake Cortex Flights Booking A2A Agent (SPCS only).

Wraps the Snowflake Cortex Agent API. The FLIGHTS_BOOKING_AGENT object
owns the system prompt that guides the agent to answer questions about
flight availability, fares, schedules, seat classes, delays, and passenger feedback.
"""
import os
import json
import re
import uuid
import requests

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    TextPart,
    TaskStatus,
    TaskState
)

from auth import get_auth_token_and_type


class SnowflakeCortexFlightsExecutor(AgentExecutor):
    """
    A2A executor that interfaces with Snowflake Cortex Agent via SPCS,
    specialised for flight availability, booking, and passenger feedback queries.
    """

    def __init__(self):
        """Initialize the executor with Snowflake configuration."""
        self.db = os.getenv("AGENT_DATABASE")
        self.schema = os.getenv("AGENT_SCHEMA")
        self.agent_name = os.getenv("AGENT_NAME")

        snowflake_host = os.getenv("SNOWFLAKE_HOST")
        snowflake_port = os.getenv("SNOWFLAKE_PORT", "443")

        if not snowflake_host:
            raise ValueError("SNOWFLAKE_HOST must be set in SPCS environment")

        if snowflake_port == "443":
            self.api_url = (
                f"https://{snowflake_host}/api/v2/databases/{self.db}"
                f"/schemas/{self.schema}/agents/{self.agent_name}:run"
            )
        else:
            self.api_url = (
                f"https://{snowflake_host}:{snowflake_port}/api/v2/databases/{self.db}"
                f"/schemas/{self.schema}/agents/{self.agent_name}:run"
            )

        print("Flights Booking A2A Agent initialized")
        print(f"  Agent: {self.db}.{self.schema}.{self.agent_name}")
        print(f"  Endpoint: {self.api_url}")

    def _parse_sse_response(self, response) -> str:
        """Parse SSE streaming response from Cortex."""
        full_text = ""

        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        full_text += data["text"]
                except json.JSONDecodeError:
                    pass

        return full_text.strip()

    _COT_PREFIXES = (
        "The user ",
        "I should ",
        "Based on my ",
        "Based on ",
        "I need to",
        "Let me ",
        "I have access to",
        "I can see that ",
        "I found ",
        "I have the ",
        "According to ",
        "This is a ",
        "This requires ",
        "This falls under ",
        "This shows ",
        "This has:",
        "This has\n",
        "Perfect!",
        "Great!",
        "Now I should ",
        "Now I need to ",
        "Now let me ",
        "The data is ",
        "The other ",
        "The reviews ",
        "Looking at ",
        "Please find the ",
        "The chart ",
        "The SQL result ",
        "Since this ",
        "Here's a visual comparison",
        "This would ",
        "The data shows",
        "As you can see",
    )

    _COT_PATTERN = re.compile(
        r"^("
        r"\d+\.\s+(?:A\s+Cortex|Query\s|Order\s|Show\s|Search\s|Get\s|Find\s"
        r"|Since\s|Limit\s|Filter\s|Check\s|Include\s|Potentially\s|Create\s"
        r"|Sort\s|Return\s|Use\s|Call\s|Look\s|Provide\s|Display\s|Fetch\s)"
        r"|"
        r"- .*(?:suitable for comparison|visualization-ready|good for visualization"
        r"|perfect for a|clean column|ranking.comparison|rows of data)[^\n]*"
        r")",
    )

    @classmethod
    def _clean_response(cls, text: str) -> str:
        """Remove duplicated content and chain-of-thought from agent responses."""
        if not text:
            return text

        # --- Phase 1: Remove duplicate paragraphs ---------------------------
        paragraphs = re.split(r"\n{2,}", text.strip())
        seen: set[str] = set()
        unique: list[str] = []
        for para in paragraphs:
            normalised = para.strip()
            if not normalised:
                continue
            if normalised in seen:
                continue
            seen.add(normalised)
            unique.append(normalised)
        text = "\n\n".join(unique)

        # --- Phase 2: Strip leading chain-of-thought lines ------------------
        lines = text.split("\n")
        first_content = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if cls._COT_PATTERN.match(stripped):
                first_content = i + 1
                continue
            if any(stripped.startswith(p) for p in cls._COT_PREFIXES):
                first_content = i + 1
                continue
            break

        if first_content > 0:
            while first_content < len(lines) and not lines[first_content].strip():
                first_content += 1
            cleaned = "\n".join(lines[first_content:]).strip()
            if cleaned:
                text = cleaned

        # --- Phase 3: Remove interior CoT paragraphs -------------------------
        paragraphs = re.split(r"\n{2,}", text.strip())
        kept: list[str] = []
        for para in paragraphs:
            lines_in = [l for l in para.split("\n") if l.strip()]
            if not lines_in:
                continue
            all_cot = True
            for l in lines_in:
                s = l.strip()
                if cls._COT_PATTERN.match(s):
                    continue
                if any(s.startswith(p) for p in cls._COT_PREFIXES):
                    continue
                if re.match(r"^Step\s+\d+:", s):
                    continue
                all_cot = False
                break
            if not all_cot:
                kept.append(para)
        text = "\n\n".join(kept) if kept else text

        # --- Phase 4: Strip trailing chain-of-thought lines ------------------
        lines = text.rstrip().split("\n")
        while lines:
            last = lines[-1].strip()
            if not last:
                lines.pop()
                continue
            if cls._COT_PATTERN.match(last):
                lines.pop()
                continue
            if any(last.startswith(p) for p in cls._COT_PREFIXES):
                lines.pop()
                continue
            break
        text = "\n".join(lines).rstrip()

        return text

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Main entry point called by A2A Protocol when a task is received."""
        try:
            incoming_text = "Hello"

            if context.message and context.message.parts:
                for part in context.message.parts:
                    actual_part = getattr(part, 'root', part)
                    if isinstance(actual_part, TextPart):
                        incoming_text = actual_part.text
                        break
                    elif hasattr(actual_part, 'text'):
                        incoming_text = actual_part.text
                        break

            print(f"[Flights Agent] Received query: {incoming_text}")

            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.working)
            )

            token, token_type = get_auth_token_and_type()

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Snowflake-Authorization-Token-Type": token_type,
                "Accept": "application/json"
            }

            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": incoming_text}]
                    }
                ]
            }

            print("[Flights Agent] Calling Snowflake Cortex API...")
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=120,
                stream=True
            )

            if response.status_code != 200:
                print(f"[Flights Agent] Snowflake API Error {response.status_code}: {response.text}")
                await event_queue.enqueue_event(
                    TaskStatus(state=TaskState.failed)
                )
                return

            content_type = response.headers.get("Content-Type", "")

            if "text/event-stream" in content_type:
                print("[Flights Agent] Receiving streaming response from Cortex...")
                final_answer = self._parse_sse_response(response)
            else:
                data = response.json()
                final_answer = "I could not retrieve flight booking information from the Cortex Agent."

                if "messages" in data:
                    for msg in reversed(data["messages"]):
                        if msg["role"] in ["assistant", "analyst"]:
                            for content in msg["content"]:
                                if content["type"] == "text":
                                    final_answer = content["text"]
                                    break
                            break

            final_answer = self._clean_response(final_answer)

            if not final_answer:
                final_answer = "I could not retrieve flight booking information from the Cortex Agent."

            print(f"[Flights Agent] Got response from Cortex ({len(final_answer)} chars)")

            response_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=final_answer)]
            )
            await event_queue.enqueue_event(response_msg)

            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.completed)
            )

        except Exception as e:
            print(f"[Flights Agent] Execution error: {str(e)}")
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.failed)
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation requests."""
        await event_queue.enqueue_event(
            TaskStatus(state=TaskState.canceled)
        )
