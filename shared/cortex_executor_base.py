"""
Base executor for Snowflake Cortex A2A agents (SPCS only).

Subclasses set two class attributes to specialise behaviour:
    _agent_label      – short display name used in log messages (e.g. "Hotels")
    _fallback_message – text returned when Cortex returns no usable content
"""
import os
import json
import uuid
import requests

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, TextPart, TaskStatus, TaskState

from auth import get_auth_token_and_type
from response_cleaner import clean_response


class CortexExecutorBase(AgentExecutor):
    """Shared A2A executor that calls the Snowflake Cortex Agent REST API."""

    _agent_label: str = "Agent"
    _fallback_message: str = "I could not retrieve an answer from the Cortex Agent."

    def __init__(self):
        self.db = os.getenv("AGENT_DATABASE")
        self.schema = os.getenv("AGENT_SCHEMA")
        self.agent_name = os.getenv("AGENT_NAME")

        snowflake_host = os.getenv("SNOWFLAKE_HOST")
        snowflake_port = os.getenv("SNOWFLAKE_PORT", "443")

        if not snowflake_host:
            raise ValueError("SNOWFLAKE_HOST must be set in SPCS environment")

        base = f"https://{snowflake_host}"
        if snowflake_port != "443":
            base = f"https://{snowflake_host}:{snowflake_port}"

        self.api_url = (
            f"{base}/api/v2/databases/{self.db}"
            f"/schemas/{self.schema}/agents/{self.agent_name}:run"
        )

        print(f"[{self._agent_label}] A2A Agent initialized")
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

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Main entry point called by A2A Protocol when a task is received."""
        try:
            incoming_text = "Hello"

            if context.message and context.message.parts:
                for part in context.message.parts:
                    actual_part = getattr(part, "root", part)
                    if isinstance(actual_part, TextPart):
                        incoming_text = actual_part.text
                        break
                    elif hasattr(actual_part, "text"):
                        incoming_text = actual_part.text
                        break

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
                ]
            }

            print(f"[{self._agent_label}] Calling Snowflake Cortex API...")
            response = requests.post(
                self.api_url, json=payload, headers=headers, timeout=120, stream=True
            )

            if response.status_code != 200:
                print(
                    f"[{self._agent_label}] Snowflake API Error "
                    f"{response.status_code}: {response.text}"
                )
                await event_queue.enqueue_event(TaskStatus(state=TaskState.failed))
                return

            content_type = response.headers.get("Content-Type", "")

            if "text/event-stream" in content_type:
                print(f"[{self._agent_label}] Receiving streaming response from Cortex...")
                final_answer = self._parse_sse_response(response)
            else:
                data = response.json()
                final_answer = self._fallback_message
                if "messages" in data:
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
            await event_queue.enqueue_event(TaskStatus(state=TaskState.failed))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation requests."""
        await event_queue.enqueue_event(TaskStatus(state=TaskState.canceled))
