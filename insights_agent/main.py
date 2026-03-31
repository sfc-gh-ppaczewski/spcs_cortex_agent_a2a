"""
Main entry point for the Snowflake Cortex Insights A2A Agent (SPCS only).

This agent wraps a Snowflake Cortex Agent and specialises it for analytical
insights: every response is structured as an executive report with
Executive Summary, Key Findings, and Recommendations sections.
"""
import os
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

from executor import SnowflakeCortexInsightsExecutor


def get_service_url() -> str:
    """Get the service URL from environment.

    For the insights agent this should be set to the internal SPCS address
    (e.g. http://cortex-a2a-agent:8001) via the SPCS_SERVICE_URL env var in
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
    agent_name = os.getenv("AGENT_NAME", "cortex_insights_agent")
    agent_description = os.getenv(
        "AGENT_DESCRIPTION",
        "A Snowflake Cortex Insights Agent that returns structured analytical "
        "reports with Executive Summary, Key Findings, and Recommendations."
    )

    insights_skill = AgentSkill(
        id="analytical_insights",
        name="Analytical Insights Report",
        description=(
            "Analyses data and returns a structured business insights report "
            "covering executive summary, key findings, and recommended actions. "
            "Best for trend analysis, anomaly investigation, and strategic questions."
        ),
        tags=["insights", "trends", "analysis", "recommendations", "forecasting", "report"],
        examples=[
            "Why is customer churn increasing?",
            "What trends do you see in our revenue data?",
            "Analyse the performance of our top products",
            "What should we focus on to improve sales next quarter?",
        ]
    )

    capabilities = AgentCapabilities(
        streaming=False,
        push_notifications=False
    )

    agent_card = AgentCard(
        name=f"Cortex Insights Agent: {agent_name}",
        description=agent_description,
        url=get_service_url(),
        version="1.0.0",
        skills=[insights_skill],
        capabilities=capabilities,
        defaultInputModes=["text"],
        defaultOutputModes=["text"]
    )

    executor = SnowflakeCortexInsightsExecutor()
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
    agent_name = os.getenv("AGENT_NAME", "cortex_insights_agent")
    print(f"Starting Snowflake Cortex Insights A2A Agent: {agent_name}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False
    )
