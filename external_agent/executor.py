"""
Executor for the external orchestrator A2A agent.

Uses a local LLM (llama.cpp) for reasoning and routes questions to one of
three destinations:
  - DATA:    factual data lookups  → Cortex Data Agent    (:8000)
  - INSIGHTS: analytical questions → Cortex Insights Agent (:8001)
  - direct answer                  → local LLM
"""
import os
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

SYSTEM_PROMPT = """You are a routing agent. Your ONLY job is to classify a question into one of three categories and respond accordingly.

RULES:
- If the question asks for specific data facts (how many, list, show me, what is the value of, count): respond with ONLY "DATA: <question>" and nothing else.
- If the question asks for analysis, trends, insights, recommendations, comparisons, forecasting, or explanations of patterns: respond with ONLY "INSIGHTS: <question>" and nothing else.
- If the question is general knowledge, math, or logic unrelated to data: respond with ONLY the answer. No thinking, no preamble.

CRITICAL: Never include your reasoning process. Output ONLY the routing command OR the direct answer.

Examples:
User: How many customers are there?
DATA: How many customers are there?

User: What tables do you have?
DATA: What tables do you have?

User: What data do you have access to?
DATA: What data do you have access to?

User: Why is customer churn increasing?
INSIGHTS: Why is customer churn increasing?

User: What trends do you see in revenue?
INSIGHTS: What trends do you see in revenue?

User: Recommend actions to improve sales next quarter.
INSIGHTS: Recommend actions to improve sales next quarter.

User: What is 2+2?
4

User: Explain the A2A protocol.
The Agent-to-Agent (A2A) protocol is a standard for AI agents to communicate with each other."""

DATA_PREFIX = "DATA:"
INSIGHTS_PREFIX = "INSIGHTS:"


class ExternalAgentExecutor(AgentExecutor):
    """
    A2A executor that uses a local LLM for reasoning and routes questions
    to the Cortex Data Agent, Cortex Insights Agent, or answers directly.
    """

    def __init__(self):
        self.llm = LLMClient()
        self.data_client = SnowflakeA2AClient()
        self.insights_client = SnowflakeA2AClient(
            url=os.getenv("INSIGHTS_A2A_AGENT_URL", "http://cortex-a2a-agent:8001")
        )
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

            # Route based on the prefix the LLM produced.
            # Handle prefix at start or after chain-of-thought leakage.
            stripped = llm_response.strip()

            def _extract_query(text: str, prefix: str) -> str:
                pos = text.index(prefix)
                query = text[pos + len(prefix):].strip()
                # Discard any trailing reasoning after the first line
                return query.split("\n")[0].strip()

            if DATA_PREFIX in stripped:
                data_query = _extract_query(stripped, DATA_PREFIX)
                print(f"[External Agent] Routing to Data Agent: {data_query}")
                response = await self.data_client.send_query(data_query)
                print(f"[External Agent] Data Agent response: {response[:200]}")
                final_answer = response

            elif INSIGHTS_PREFIX in stripped:
                insights_query = _extract_query(stripped, INSIGHTS_PREFIX)
                print(f"[External Agent] Routing to Insights Agent: {insights_query}")
                response = await self.insights_client.send_query(insights_query)
                print(f"[External Agent] Insights Agent response: {response[:200]}")
                final_answer = response

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
