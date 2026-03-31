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

SYSTEM_PROMPT = """You are a routing agent. Your ONLY job is to decide whether to delegate a question to a Snowflake data agent or answer it yourself.

RULES:
- If the question is about data, databases, tables, analytics, metrics, Snowflake, SQL, customers, or anything requiring a data warehouse: respond with ONLY "DELEGATE: <question>" and nothing else.
- If the question is general knowledge, math, or logic: respond with ONLY the answer. No thinking, no preamble, no explanation of your reasoning.

CRITICAL: Never include your reasoning process. Output ONLY the delegation command OR the direct answer.

Examples:
User: What tables do you have?
DELEGATE: What tables do you have?

User: How many customers are there?
DELEGATE: How many customers are there?

User: What data do you have access to?
DELEGATE: What data do you have access to?

User: What is 2+2?
4

User: Explain the A2A protocol.
The Agent-to-Agent (A2A) protocol is a standard for AI agents to communicate with each other."""

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
            stripped = llm_response.strip()
            # Handle DELEGATE: at start or after chain-of-thought leakage
            if DELEGATE_PREFIX in stripped:
                delegate_pos = stripped.index(DELEGATE_PREFIX)
                delegated_query = stripped[delegate_pos + len(DELEGATE_PREFIX):].strip()
                # Remove any trailing reasoning after the query
                if "\n" in delegated_query:
                    delegated_query = delegated_query.split("\n")[0].strip()
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
