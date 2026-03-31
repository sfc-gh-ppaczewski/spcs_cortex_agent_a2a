"""
Base executor for Snowflake Cortex A2A agents (SPCS only).

Subclasses set two class attributes to specialise behaviour:
    _agent_label      – short display name used in log messages (e.g. "Hotels")
    _fallback_message – text returned when Cortex returns no usable content
"""
import os
import json
import uuid
import httpx

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, TextPart, TaskStatus, TaskState

from auth import get_auth_token_and_type
from response_cleaner import clean_response


def _extract_text_from_message(message) -> str:
    """Extract the first text part from an A2A message. Returns 'Hello' if none found."""
    if not message or not message.parts:
        return "Hello"
    for part in message.parts:
        actual_part = getattr(part, "root", part)
        if isinstance(actual_part, TextPart):
            return actual_part.text
        if hasattr(actual_part, "text"):
            return actual_part.text
    return "Hello"


class CortexExecutorBase(AgentExecutor):
    """Shared A2A executor that calls the Snowflake Cortex Agent REST API."""

    _agent_label: str = "Agent"
    _fallback_message: str = "I could not retrieve an answer from the Cortex Agent."

    def __init__(self):
        self.db = os.getenv("AGENT_DATABASE")
        self.schema = os.getenv("AGENT_SCHEMA")
        self.agent_name = os.getenv("AGENT_NAME")

        if not self.agent_name:
            raise ValueError("AGENT_NAME environment variable must be set")

        snowflake_host = os.getenv("SNOWFLAKE_HOST")
        snowflake_port = os.getenv("SNOWFLAKE_PORT", "443")

        if not snowflake_host:
            raise ValueError("SNOWFLAKE_HOST must be set in SPCS environment")

        base = f"https://{snowflake_host}"
        if int(snowflake_port) != 443:
            base = f"https://{snowflake_host}:{snowflake_port}"

        self.api_url = (
            f"{base}/api/v2/databases/{self.db}"
            f"/schemas/{self.schema}/agents/{self.agent_name}:run"
        )

        print(f"[{self._agent_label}] A2A Agent initialized")
        print(f"  Agent: {self.db}.{self.schema}.{self.agent_name}")
        print(f"  Endpoint: {self.api_url}")

    def _parse_sse_response(self, text: str) -> str:
        """Parse SSE response text from Cortex.

        Only collects text from ``response.text.delta`` events and ignores
        ``response.thinking.delta`` (chain-of-thought) events so that
        reasoning tokens never leak into the final answer.
        """
        full_text = ""
        current_event = ""
        for line in text.split("\n"):
            if line.startswith("event:"):
                current_event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                # Only keep answer tokens, skip thinking/reasoning tokens
                if current_event == "response.thinking.delta":
                    continue
                try:
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        full_text += data["text"]
                except json.JSONDecodeError:
                    pass
        return full_text.strip()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Main entry point called by A2A Protocol when a task is received."""
        try:
            incoming_text = _extract_text_from_message(context.message)

            print(f"[{self._agent_label}] Received query: {incoming_text}")

            await event_queue.enqueue_event(TaskStatus(state=TaskState.working))

            token, token_type = get_auth_token_and_type()

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Snowflake-Authorization-Token-Type": token_type,
                "Accept": "application/json",
            }

            payload = {
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": incoming_text}]}
                ],
                "stream": False,
            }

            print(f"[{self._agent_label}] Calling Snowflake Cortex API...")

            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)

            if response.status_code != 200:
                print(
                    f"[{self._agent_label}] Snowflake API Error "
                    f"{response.status_code}: {response.text}"
                )
                error_msg = Message(
                    messageId=str(uuid.uuid4()),
                    role="agent",
                    parts=[TextPart(text=f"Cortex API error {response.status_code}.")],
                )
                await event_queue.enqueue_event(error_msg)
                await event_queue.enqueue_event(TaskStatus(state=TaskState.failed))
                return

            content_type = response.headers.get("content-type", "")

            if "text/event-stream" in content_type:
                print(f"[{self._agent_label}] Parsing SSE response from Cortex...")
                final_answer = self._parse_sse_response(response.text)
            else:
                data = response.json()
                final_answer = self._fallback_message

                # New Cortex Agent API format: top-level "content" array
                # Concatenate ALL text items (the agent may split its answer
                # across multiple content entries).
                if "content" in data:
                    text_parts = []
                    for item in data["content"]:
                        if item.get("type") == "text" and "text" in item:
                            text_parts.append(item["text"])
                    if text_parts:
                        final_answer = "\n\n".join(text_parts)

                # Legacy format: "messages" array with role-based extraction
                elif "messages" in data:
                    for msg in reversed(data["messages"]):
                        if msg["role"] in ["assistant", "analyst"]:
                            for content in msg["content"]:
                                if content["type"] == "text":
                                    final_answer = content["text"]
                                    break
                            break

            final_answer = clean_response(final_answer)

            if not final_answer:
                final_answer = self._fallback_message

            print(f"[{self._agent_label}] Got response from Cortex ({len(final_answer)} chars)")

            response_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=final_answer)],
            )
            await event_queue.enqueue_event(response_msg)
            await event_queue.enqueue_event(TaskStatus(state=TaskState.completed))

        except Exception as e:
            print(f"[{self._agent_label}] Execution error: {str(e)}")
            error_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=f"An error occurred: {str(e)}")],
            )
            await event_queue.enqueue_event(error_msg)
            await event_queue.enqueue_event(TaskStatus(state=TaskState.failed))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation requests."""
        await event_queue.enqueue_event(TaskStatus(state=TaskState.canceled))
