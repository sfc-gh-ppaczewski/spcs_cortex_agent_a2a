# Dockerfile for Snowflake Cortex A2A Agent
# Optimized for Snowpark Container Services (SPCS) deployment
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY auth.py .
COPY executor.py .
COPY main.py .

# Expose the A2A server port
EXPOSE 8000

# Health check for SPCS
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/.well-known/agent-card.json || exit 1

# Run the server (no reload in production)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
