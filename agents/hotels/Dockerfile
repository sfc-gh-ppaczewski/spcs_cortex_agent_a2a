# Dockerfile for Hotels Booking A2A Agent
# Build from repo root: docker build -f agents/hotels/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY agents/hotels/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared utilities (auth, response cleaner, base executor)
COPY shared/ .

# Agent-specific files
COPY agents/hotels/main.py .
COPY agents/hotels/executor.py .
COPY agents/hotels/test_hotels_agent.py .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/.well-known/agent-card.json || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
