"""
Main entry point for the External Orchestrator A2A Agent (SPCS).

This agent uses a local LLM (llama.cpp sidecar) for reasoning and routes
travel questions to either the Hotels Booking Agent or the Flights Booking Agent.
"""
import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from executor import ExternalAgentExecutor


def get_service_url() -> str:
    """Get the service URL from environment."""
    ingress_url = os.getenv("SPCS_SERVICE_URL")
    if ingress_url:
        return ingress_url.rstrip("/")

    service_name = os.getenv("SNOWFLAKE_SERVICE_NAME")
    if service_name:
        return f"https://{service_name}"

    return "http://0.0.0.0:9000"


def create_app() -> object:
    """Create and configure the A2A Starlette application."""
    agent_name = os.getenv("AGENT_NAME", "travel_orchestrator")
    agent_description = os.getenv(
        "AGENT_DESCRIPTION",
        "A travel booking orchestrator powered by a local LLM. Routes hotel questions "
        "to the Hotels Booking Agent and flight questions to the Flights Booking Agent "
        "via A2A protocol. Answers general questions directly.",
    )

    hotels_skill = AgentSkill(
        id="hotel_booking_queries",
        name="Hotel Booking Queries",
        description=(
            "Routes hotel-related questions to the Hotels Booking Agent, which answers "
            "queries about availability, pricing, amenities, guest ratings, and reviews "
            "for our global hotel portfolio."
        ),
        tags=["hotels", "accommodation", "booking", "travel", "availability"],
        examples=[
            "Show me available 5-star hotels in Paris",
            "What is the price per night at The Grand Paris?",
            "List hotels with free cancellation in Tokyo",
            "What are guests saying about the Bali Zen Resort?",
        ],
    )

    flights_skill = AgentSkill(
        id="flight_booking_queries",
        name="Flight Booking Queries",
        description=(
            "Routes flight-related questions to the Flights Booking Agent, which answers "
            "queries about availability, fares, schedules, seat classes, delays, and "
            "passenger feedback for our global flight inventory."
        ),
        tags=["flights", "airlines", "booking", "travel", "fares"],
        examples=[
            "Find available flights from JFK to LHR tomorrow",
            "What is the cheapest business class fare to Tokyo?",
            "How delayed is United Airlines on average?",
            "What are passengers saying about Qatar Airways?",
        ],
    )

    general_skill = AgentSkill(
        id="general_knowledge",
        name="General Knowledge",
        description=(
            "Answers general knowledge, math, logic, and conversational "
            "questions using the local LLM without external delegation."
        ),
        tags=["general", "knowledge", "math", "logic"],
        examples=[
            "What is 2+2?",
            "Explain the A2A protocol",
            "Write a haiku about travel",
        ],
    )

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False,
    )

    agent_card = AgentCard(
        name=f"Travel Orchestrator: {agent_name}",
        description=agent_description,
        url=get_service_url(),
        version="1.0.0",
        skills=[hotels_skill, flights_skill, general_skill],
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
    )

    executor = ExternalAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    return a2a_app.build(
        agent_card_url="/.well-known/agent-card.json",
        rpc_url="/",
    )


app = create_app()


if __name__ == "__main__":
    agent_name = os.getenv("AGENT_NAME", "travel_orchestrator")
    print(f"Starting Travel Orchestrator A2A Agent: {agent_name}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        reload=False,
    )
