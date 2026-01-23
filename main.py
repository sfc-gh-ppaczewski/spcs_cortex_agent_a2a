"""
Main entry point for the Snowflake Cortex A2A Agent.

This server exposes any Snowflake Cortex Agent via the A2A protocol,
allowing other AI agents to interact with it through a standardized interface.

Supports both SPCS (Snowpark Container Services) and local deployment:
- SPCS: Uses session token authentication and public endpoint
- Local: Uses JWT key-pair authentication
"""
import os
import uvicorn
from dotenv import load_dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

# Import our custom executor and auth helper
from executor import SnowflakeCortexExecutor
from auth import is_running_in_spcs

load_dotenv()


def get_service_url() -> str:
    """
    Get the service URL based on the deployment environment.
    
    In SPCS, uses the public endpoint URL from environment.
    Locally, defaults to localhost:8000.
    
    Returns:
        The service URL string
    """
    if is_running_in_spcs():
        # SPCS provides the ingress URL via environment variable
        # This should be set in the service spec or computed from service name
        ingress_url = os.getenv("SPCS_SERVICE_URL")
        if ingress_url:
            return ingress_url.rstrip("/")
        
        # Fallback: construct from SPCS environment variables if available
        # Format: https://<service>-<org>-<account>.snowflakecomputing.app
        service_name = os.getenv("SNOWFLAKE_SERVICE_NAME")
        if service_name:
            return f"https://{service_name}"
        
        # Default fallback for SPCS (container port)
        return "http://0.0.0.0:8000"
    
    return os.getenv("AGENT_URL", "http://localhost:8000")


def create_app() -> A2AStarletteApplication:
    """Create and configure the A2A Starlette application."""
    
    # Get agent configuration from environment
    agent_name = os.getenv("AGENT_NAME", "cortex_agent")
    agent_description = os.getenv(
        "AGENT_DESCRIPTION", 
        "A Snowflake Cortex Agent exposed via the A2A protocol."
    )
    
    # 1. Define Skills
    # This tells other agents what we can do (Discovery)
    cortex_skill = AgentSkill(
        id="query_cortex_agent",
        name="Cortex Agent Query",
        description=f"Sends queries to the Snowflake Cortex Agent ({agent_name}) and returns intelligent responses.",
        tags=["snowflake", "cortex", "ai", "analytics"],
        examples=[
            "What data do you have access to?",
            "Summarize the available information",
            "Answer questions about the data"
        ]
    )

    # 2. Define Agent Capabilities
    # Note: Full streaming support requires additional A2A SDK configuration
    # Currently using non-streaming mode for simplicity
    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False
    )

    # 3. Define the Agent Card
    service_url = get_service_url()
    agent_card = AgentCard(
        name=f"Cortex Agent: {agent_name}",
        description=agent_description,
        url=service_url,
        version="1.0.0",
        skills=[cortex_skill],
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"]
    )

    # 4. Create the request handler with executor and task store
    executor = SnowflakeCortexExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store
    )

    # 5. Initialize the Application
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    
    # Build the Starlette ASGI app
    # Routes:
    #  - /.well-known/agent-card.json (Discovery)
    #  - / (JSON-RPC endpoint for tasks)
    starlette_app = a2a_app.build(
        agent_card_url="/.well-known/agent-card.json",
        rpc_url="/"
    )
    
    return starlette_app


# Create the app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    agent_name = os.getenv("AGENT_NAME", "cortex_agent")
    service_url = get_service_url()
    is_spcs = is_running_in_spcs()
    
    print(f"🚀 Starting Snowflake Cortex A2A Agent: {agent_name}")
    print(f"   Mode: {'SPCS' if is_spcs else 'Local'}")
    print("=" * 50)
    print(f"📋 Discovery endpoint: {service_url}/.well-known/agent-card.json")
    print(f"📨 Task endpoint: {service_url}/")
    print("=" * 50)
    
    # In SPCS, bind to 0.0.0.0 to accept external connections
    # Disable reload in production (SPCS)
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=not is_spcs
    )
