"""
Executor for the external orchestrator A2A agent.

Uses a local LLM (llama.cpp) for reasoning and routes questions to one of
three destinations:
  - HOTELS:  hotel booking questions  → Hotels Booking Agent  (:8000)
  - FLIGHTS: flight booking questions → Flights Booking Agent (:8001)
  - direct answer                      → local LLM
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

SYSTEM_PROMPT = """You are a routing agent. Your ONLY job is to classify a travel question into one of three categories and respond accordingly.

RULES:
- If the question is about hotels, accommodation, room availability, hotel prices, check-in/check-out, hotel amenities, hotel ratings, or hotel reviews: respond with ONLY "HOTELS: <question>" and nothing else.
- If the question is about flights, airlines, routes, fare prices, seat class, departure/arrival times, flight delays, or passenger feedback: respond with ONLY "FLIGHTS: <question>" and nothing else.
- If the question is general knowledge, math, or logic unrelated to travel bookings: respond with ONLY the answer. No thinking, no preamble.

CRITICAL: Never include your reasoning process. Output ONLY the routing command OR the direct answer.

Examples:
User: Show me available 5-star hotels in Paris.
HOTELS: Show me available 5-star hotels in Paris.

User: What is the price per night at The Grand Paris?
HOTELS: What is the price per night at The Grand Paris?

User: What are guests saying about the Bali Zen Resort?
HOTELS: What are guests saying about the Bali Zen Resort?

User: Find available flights from JFK to LHR tomorrow.
FLIGHTS: Find available flights from JFK to LHR tomorrow.

User: What is the cheapest business class fare to Tokyo?
FLIGHTS: What is the cheapest business class fare to Tokyo?

User: How delayed is United Airlines on average?
FLIGHTS: How delayed is United Airlines on average?

User: What are passengers saying about Qatar Airways?
FLIGHTS: What are passengers saying about Qatar Airways?

User: What is 2+2?
4

User: Explain the A2A protocol.
The Agent-to-Agent (A2A) protocol is a standard for AI agents to communicate with each other."""

HOTELS_PREFIX = "HOTELS:"
FLIGHTS_PREFIX = "FLIGHTS:"


class ExternalAgentExecutor(AgentExecutor):
    """
    A2A executor that uses a local LLM for reasoning and routes questions
    to the Hotels Booking Agent, Flights Booking Agent, or answers directly.
    """

    def __init__(self):
        self.llm = LLMClient()
        self.hotels_client = SnowflakeA2AClient(
            url=os.getenv("HOTELS_A2A_AGENT_URL", "http://travel-a2a-agent:8000")
        )
        self.flights_client = SnowflakeA2AClient(
            url=os.getenv("FLIGHTS_A2A_AGENT_URL", "http://travel-a2a-agent:8001")
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

            if HOTELS_PREFIX in stripped:
                hotels_query = _extract_query(stripped, HOTELS_PREFIX)
                print(f"[External Agent] Routing to Hotels Agent: {hotels_query}")
                response = await self.hotels_client.send_query(hotels_query)
                print(f"[External Agent] Hotels Agent response: {response[:200]}")
                final_answer = response

            elif FLIGHTS_PREFIX in stripped:
                flights_query = _extract_query(stripped, FLIGHTS_PREFIX)
                print(f"[External Agent] Routing to Flights Agent: {flights_query}")
                response = await self.flights_client.send_query(flights_query)
                print(f"[External Agent] Flights Agent response: {response[:200]}")
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
