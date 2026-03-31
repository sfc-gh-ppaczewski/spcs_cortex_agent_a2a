"""
Main entry point for the Snowflake Cortex Flights Booking A2A Agent (SPCS only).

This agent wraps a Snowflake Cortex Agent and specialises it for flight booking:
answering questions about flight availability, fares, schedules, seat classes,
delays, and passenger feedback from the TravelDemo BOOKING schema.
"""
import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from executor import SnowflakeCortexFlightsExecutor


def get_service_url() -> str:
    """Get the service URL from environment.

    For the flights agent this should be set to the internal SPCS address
    (e.g. http://travel-a2a-agent:8001) via the SPCS_SERVICE_URL env var in
    the service spec so the agent card advertises the correct internal URL.
    """
    ingress_url = os.getenv("SPCS_SERVICE_URL")
    if ingress_url:
        return ingress_url.rstrip("/")

    service_name = os.getenv("SNOWFLAKE_SERVICE_NAME")
    if service_name:
        return f"https://{service_name}:8001"

    return "http://0.0.0.0:8001"


def create_app() -> A2AStarletteApplication:
    """Create and configure the A2A Starlette application."""
    agent_name = os.getenv("AGENT_NAME", "flights_booking_agent")
    agent_description = os.getenv(
        "AGENT_DESCRIPTION",
        "A Snowflake Cortex Flights Booking Agent that answers questions about "
        "flight availability, fares, schedules, seat classes, delays, and passenger feedback."
    )

    flights_skill = AgentSkill(
        id="flight_search_booking",
        name="Flight Search & Booking",
        description=(
            "Queries the TravelDemo Flights Booking Agent for flight availability, "
            "fares, schedules, seat classes, airline performance, and passenger feedback. "
            "Best for route searches, price comparisons, and travel planning."
        ),
        tags=["flights", "booking", "airlines", "travel", "fares", "schedules"],
        examples=[
            "Find available flights from JFK to LHR tomorrow",
            "What is the cheapest business class fare to Tokyo?",
            "How delayed is United Airlines on average?",
            "What are passengers saying about Air France flights?",
        ]
    )

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False
    )

    agent_card = AgentCard(
        name=f"Flights Booking Agent: {agent_name}",
        description=agent_description,
        url=get_service_url(),
        version="1.0.0",
        skills=[flights_skill],
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"]
    )

    executor = SnowflakeCortexFlightsExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )

    return a2a_app.build(
        agent_card_url="/.well-known/agent-card.json",
        rpc_url="/"
    )


app = create_app()


if __name__ == "__main__":
    agent_name = os.getenv("AGENT_NAME", "flights_booking_agent")
    print(f"Starting Flights Booking A2A Agent: {agent_name}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False
    )
