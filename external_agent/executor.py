"""
Executor for the external orchestrator A2A agent.

Uses a local LLM (llama.cpp) for reasoning and delegates Snowflake data
questions to the Cortex A2A agent via A2A protocol.
"""
import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    TextPart,
    TaskStatus,
    TaskState,
)

from llm_client import LLMClient
from snowflake_a2a_client import SnowflakeA2AClient

SYSTEM_PROMPT = """You are an orchestrator agent. You have access to a Snowflake data agent \
that can answer questions about data stored in Snowflake, run analytics queries, \
and provide information about databases, tables, and their contents.

When you receive a user question:

1. If the question is about data, databases, tables, analytics, metrics, \
   Snowflake, SQL, or anything that requires querying a data warehouse — \
   you MUST delegate to the Snowflake agent. Respond with EXACTLY this format:
   DELEGATE: <the question to forward to the Snowflake agent>

2. If the question is general knowledge, math, logic, or something you can \
   answer without data access — answer it directly.

Examples:
- "What tables do you have?" → DELEGATE: What tables do you have?
- "How many customers are there?" → DELEGATE: How many customers are there?
- "What data do you have access to?" → DELEGATE: What data do you have access to?
- "What is 2+2?" → The answer is 4.
- "Explain what A2A protocol is" → (answer directly)
"""

DELEGATE_PREFIX = "DELEGATE:"


class ExternalAgentExecutor(AgentExecutor):
    """
    A2A executor that uses a local LLM for reasoning and delegates
    data questions to the Snowflake Cortex A2A agent.
    """

    def __init__(self):
        self.llm = LLMClient()
        self.snowflake_client = SnowflakeA2AClient()
        print("External agent executor initialized")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Process an incoming A2A message."""
        try:
            # Extract user text from the incoming message
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

            print(f"[External Agent] Received: {incoming_text}")

            await event_queue.enqueue_event(TaskStatus(state=TaskState.working))

            # Ask the local LLM to decide: answer directly or delegate
            print("[External Agent] Consulting local LLM...")
            llm_response = self.llm.complete(SYSTEM_PROMPT, incoming_text)
            print(f"[External Agent] LLM response: {llm_response[:200]}")

            # Check if LLM wants to delegate to the Snowflake agent
            if llm_response.strip().startswith(DELEGATE_PREFIX):
                delegated_query = llm_response.strip()[len(DELEGATE_PREFIX):].strip()
                print(f"[External Agent] Delegating to Snowflake agent: {delegated_query}")

                snowflake_response = await self.snowflake_client.send_query(
                    delegated_query
                )
                print(
                    f"[External Agent] Snowflake response: "
                    f"{snowflake_response[:200]}"
                )
                final_answer = snowflake_response
            else:
                # LLM answered directly
                final_answer = llm_response

            if not final_answer:
                final_answer = "I was unable to generate a response."

            print(f"[External Agent] Final answer ({len(final_answer)} chars)")

            response_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=final_answer)],
            )
            await event_queue.enqueue_event(response_msg)
            await event_queue.enqueue_event(TaskStatus(state=TaskState.completed))

        except Exception as e:
            print(f"[External Agent] Error: {e}")
            error_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=f"Error: {str(e)}")],
            )
            await event_queue.enqueue_event(error_msg)
            await event_queue.enqueue_event(TaskStatus(state=TaskState.failed))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation."""
        await event_queue.enqueue_event(TaskStatus(state=TaskState.canceled))
