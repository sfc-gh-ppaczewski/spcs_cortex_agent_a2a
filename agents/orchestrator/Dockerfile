# Dockerfile for Travel Orchestrator Agent
# Build from repo root: docker build -f agents/orchestrator/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY agents/orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared utilities (response cleaner, auth)
COPY shared/ .

# Agent-specific files
COPY agents/orchestrator/llm_client.py .
COPY agents/orchestrator/snowflake_a2a_client.py .
COPY agents/orchestrator/executor.py .
COPY agents/orchestrator/main.py .

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9000/.well-known/agent-card.json || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
