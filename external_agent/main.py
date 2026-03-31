"""
Main entry point for the External Orchestrator A2A Agent (SPCS).

This agent uses a local LLM (llama.cpp sidecar) for reasoning and
delegates data questions to the Snowflake Cortex A2A agent.
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
    agent_name = os.getenv("AGENT_NAME", "external_orchestrator")
    agent_description = os.getenv(
        "AGENT_DESCRIPTION",
        "An external orchestrator agent powered by a local open-source LLM. "
        "Delegates Snowflake data questions to a Cortex Agent via A2A protocol.",
    )

    orchestration_skill = AgentSkill(
        id="orchestrate_query",
        name="Query Orchestration",
        description=(
            "Analyzes user questions using a local LLM and either answers "
            "directly or delegates data-related questions to a Snowflake "
            "Cortex Agent via A2A protocol."
        ),
        tags=["orchestration", "snowflake", "data", "analytics", "a2a"],
        examples=[
            "What data do you have access to?",
            "How many customers are in the database?",
            "What is the meaning of life?",
            "Summarize the sales data",
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
            "Write a haiku about snow",
        ],
    )

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False,
    )

    agent_card = AgentCard(
        name=f"External Agent: {agent_name}",
        description=agent_description,
        url=get_service_url(),
        version="1.0.0",
        skills=[orchestration_skill, general_skill],
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
    agent_name = os.getenv("AGENT_NAME", "external_orchestrator")
    print(f"Starting External Orchestrator A2A Agent: {agent_name}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        reload=False,
    )
