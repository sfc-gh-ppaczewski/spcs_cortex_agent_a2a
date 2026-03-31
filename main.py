"""
Main entry point for the Snowflake Cortex A2A Agent (SPCS only).
"""
import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from executor import SnowflakeCortexExecutor


def get_service_url() -> str:
    """Get the service URL from environment."""
    ingress_url = os.getenv("SPCS_SERVICE_URL")
    if ingress_url:
        return ingress_url.rstrip("/")
    
    service_name = os.getenv("SNOWFLAKE_SERVICE_NAME")
    if service_name:
        return f"https://{service_name}"
    
    return "http://0.0.0.0:8000"


def create_app() -> A2AStarletteApplication:
    """Create and configure the A2A Starlette application."""
    agent_name = os.getenv("AGENT_NAME", "cortex_agent")
    agent_description = os.getenv(
        "AGENT_DESCRIPTION", 
        "A Snowflake Cortex Agent exposed via the A2A protocol."
    )
    
    cortex_skill = AgentSkill(
        id="hotel_search_booking",
        name="Hotel Search & Booking",
        description=(
            "Queries the TravelDemo Hotels Booking Agent for hotel availability, "
            "pricing, amenities, guest ratings, and room types across our global portfolio."
        ),
        tags=["snowflake", "cortex", "hotels", "booking", "travel"],
        examples=[
            "Show available 5-star hotels in Paris",
            "What is the price per night at The Grand Paris?",
            "List hotels with free cancellation in Tokyo",
            "What are guests saying about Hotel Bella Vista?",
        ]
    )

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False
    )

    agent_card = AgentCard(
        name=f"Hotels Booking Agent: {agent_name}",
        description=agent_description,
        url=get_service_url(),
        version="1.0.0",
        skills=[cortex_skill],
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"]
    )

    executor = SnowflakeCortexExecutor()
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
    agent_name = os.getenv("AGENT_NAME", "cortex_agent")
    print(f"Starting Hotels Booking A2A Agent: {agent_name}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
