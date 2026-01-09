"""
Main entry point for the Snowflake Cortex A2A Agent.

This server exposes any Snowflake Cortex Agent via the A2A protocol,
allowing other AI agents to interact with it through a standardized interface.
"""
import os
import uvicorn
from dotenv import load_dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

# Import our custom executor
from executor import SnowflakeCortexExecutor

load_dotenv()


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
    agent_card = AgentCard(
        name=f"Cortex Agent: {agent_name}",
        description=agent_description,
        url=os.getenv("AGENT_URL", "http://localhost:8000"),
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
    #  - /.well-known/agent.json (Discovery)
    #  - / (JSON-RPC endpoint for tasks)
    starlette_app = a2a_app.build(
        agent_card_url="/.well-known/agent.json",
        rpc_url="/"
    )
    
    return starlette_app


# Create the app instance for uvicorn
app = create_app()


if __name__ == "__main__":
    agent_name = os.getenv("AGENT_NAME", "cortex_agent")
    print(f"🚀 Starting Snowflake Cortex A2A Agent: {agent_name}")
    print("=" * 50)
    print("📋 Discovery endpoint: http://localhost:8000/.well-known/agent.json")
    print("📨 Task endpoint: http://localhost:8000/")
    print("=" * 50)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
