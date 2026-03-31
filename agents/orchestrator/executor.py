"""
Executor for the Travel Orchestrator A2A agent.

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
from a2a.types import Message, TextPart, TaskStatus, TaskState

from llm_client import LLMClient
from snowflake_a2a_client import SnowflakeA2AClient
from cortex_executor_base import _extract_text_from_message
from response_cleaner import clean_response

SYSTEM_PROMPT = """You are a routing agent. Your ONLY job is to classify a travel question into one of three categories and respond accordingly.

RULES:
- If the question is about hotels, accommodation, room availability, hotel prices, check-in/check-out, hotel amenities, hotel ratings, or hotel reviews: respond with ONLY "HOTELS: <question>" and nothing else.
- If the question is about flights, airlines, routes, fare prices, seat class, departure/arrival times, flight delays, or passenger feedback: respond with ONLY "FLIGHTS: <question>" and nothing else.
- If the question is general knowledge, math, or logic unrelated to travel bookings: respond with ONLY the answer. No thinking, no preamble.

CRITICAL: Never include your reasoning process. Output ONLY the routing command OR the direct answer.

Examples:
User: Show me available 5-star hotels in Paris.
HOTELS: Show me available 5-star hotels in Paris.

User: Find business class flights from JFK to London.
FLIGHTS: Find business class flights from JFK to London.

User: What is 2+2?
4
"""

HOTELS_PREFIX = "HOTELS:"
FLIGHTS_PREFIX = "FLIGHTS:"


class TravelOrchestratorExecutor(AgentExecutor):
    def __init__(self):
        self.llm = LLMClient()
        self.hotels_client = SnowflakeA2AClient(
            url=os.getenv("HOTELS_A2A_AGENT_URL", "http://travel-a2a-agent:8000")
        )
        self.flights_client = SnowflakeA2AClient(
            url=os.getenv("FLIGHTS_A2A_AGENT_URL", "http://travel-a2a-agent:8001")
        )
        print("Travel orchestrator executor initialized")

    @staticmethod
    def _extract_query(text: str, prefix: str) -> str:
        """Extract the query after a routing prefix, taking only the first line."""
        pos = text.index(prefix)
        query = text[pos + len(prefix):].strip()
        return query.split("\n")[0].strip()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            incoming_text = _extract_text_from_message(context.message)

            print(f"[Travel Orchestrator] Received: {incoming_text}")
            await event_queue.enqueue_event(TaskStatus(state=TaskState.working))

            llm_response = await self.llm.complete(SYSTEM_PROMPT, incoming_text)

            stripped = llm_response.strip()

            if HOTELS_PREFIX in stripped:
                hotels_query = self._extract_query(stripped, HOTELS_PREFIX)
                final_answer = await self.hotels_client.send_query(hotels_query)
            elif FLIGHTS_PREFIX in stripped:
                flights_query = self._extract_query(stripped, FLIGHTS_PREFIX)
                final_answer = await self.flights_client.send_query(flights_query)
            else:
                final_answer = clean_response(llm_response)

            if not final_answer:
                final_answer = "I was unable to generate a response."

            response_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=final_answer)],
            )
            await event_queue.enqueue_event(response_msg)
            await event_queue.enqueue_event(TaskStatus(state=TaskState.completed))

        except Exception as e:
            print(f"[Travel Orchestrator] Error: {e}")
            error_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=f"Error: {str(e)}")],
            )
            await event_queue.enqueue_event(error_msg)
            await event_queue.enqueue_event(TaskStatus(state=TaskState.failed))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await event_queue.enqueue_event(TaskStatus(state=TaskState.canceled))
