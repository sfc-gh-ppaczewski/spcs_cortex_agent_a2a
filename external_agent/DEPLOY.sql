-- ============================================================================
-- DEPLOY.sql — Deploy the Travel Orchestrator A2A Agent on SPCS
--
-- This service runs two containers:
--   1. llm-server:       llama.cpp serving a local Qwen2.5-1.5B model (port 8080)
--   2. external-agent:   Python A2A server that orchestrates travel queries (port 9000)
--
-- The orchestrator routes:
--   HOTELS: questions → Hotels Booking Agent (http://travel-a2a-agent:8000)
--   FLIGHTS: questions → Flights Booking Agent (http://travel-a2a-agent:8001)
--   General questions → answered directly by the local LLM
--
-- Prerequisites:
--   - The TRAVEL_A2A_AGENT service must be deployed and running (see README)
--   - You have run download_model.sh to upload the GGUF model to a stage
--   - You have built and pushed both Docker images to the SPCS image registry
--
-- Replace these placeholders before running:
--   <AGENT_DATABASE>  — Database where resources will be created (e.g. TRAVEL_DEMO)
--   <AGENT_SCHEMA>    — Schema where resources will be created (e.g. BOOKING)
--   <REPO_URL>        — Image repository URL (from SHOW IMAGE REPOSITORIES)
-- ============================================================================

-- Step 1: Set context
USE ROLE ACCOUNTADMIN;
USE DATABASE <AGENT_DATABASE>;
USE SCHEMA <AGENT_SCHEMA>;

-- Step 2: Create compute pool (CPU — no GPU needed for 1.5B quantized model)
CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_ORCHESTRATOR_POOL
    MIN_NODES = 1
    MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_S   -- 2 vCPU, 8 GB RAM (sufficient for Q4 1.5B model)
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 1800;

-- If 8GB is tight, use CPU_X64_M (4 vCPU, 16 GB RAM) instead:
-- INSTANCE_FAMILY = CPU_X64_M

-- Step 3: Create image repository (if not already created)
CREATE IMAGE REPOSITORY IF NOT EXISTS A2A_IMAGES;

-- Get repository URL
SHOW IMAGE REPOSITORIES LIKE 'A2A_IMAGES';
-- Copy the 'repository_url' value — you'll need it for docker push

-- Step 4: Create stage for the LLM model (if not already created by download_model.sh)
CREATE STAGE IF NOT EXISTS LLM_MODELS
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- Verify model is uploaded
LIST @LLM_MODELS;
-- You should see: qwen2.5-1.5b-instruct-q4_k_m.gguf

-- Step 5: Build and push Docker images
-- Run these commands from your terminal (not in Snowflake):
--
--   # Set variables
--   export REPO_URL="<repository_url>"
--   export SNOW_CONNECTION="<YOUR_CONNECTION>"
--
--   # Build and push the external agent image
--   cd external_agent
--   docker build --platform linux/amd64 -t external-a2a-agent:latest .
--   snow spcs image-registry login --connection $SNOW_CONNECTION
--   docker tag external-a2a-agent:latest $REPO_URL/external-a2a-agent:latest
--   docker push $REPO_URL/external-a2a-agent:latest

-- Step 6: Create the service with two containers
-- NOTE: Replace <AGENT_DATABASE> and <AGENT_SCHEMA>.
--       The internal DNS for the Cortex agents service is http://travel-a2a-agent:<port>

CREATE SERVICE TRAVEL_ORCHESTRATOR
    IN COMPUTE POOL TRAVEL_ORCHESTRATOR_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: llm-server
      image: ghcr.io/ggerganov/llama.cpp:server
      args:
        - "--model"
        - "/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
        - "--host"
        - "0.0.0.0"
        - "--port"
        - "8080"
        - "--ctx-size"
        - "2048"
        - "--threads"
        - "2"
      resources:
        requests:
          cpu: 1
          memory: 4Gi
        limits:
          cpu: 1.5
          memory: 5Gi
      volumeMounts:
        - name: models
          mountPath: /models
      readinessProbe:
        httpGet:
          path: /health
          port: 8080
        initialDelaySeconds: 30
        periodSeconds: 10

    - name: external-agent
      image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/external-a2a-agent:latest
      env:
        AGENT_NAME: travel_orchestrator
        AGENT_DESCRIPTION: "Travel booking orchestrator that routes hotel questions to the Hotels Booking Agent and flight questions to the Flights Booking Agent via A2A protocol."
        LLM_BASE_URL: "http://localhost:8080/v1"
        LLM_MODEL: "local-model"
        HOTELS_A2A_AGENT_URL: "http://travel-a2a-agent:8000"
        FLIGHTS_A2A_AGENT_URL: "http://travel-a2a-agent:8001"
      resources:
        requests:
          cpu: 0.5
          memory: 512Mi
        limits:
          cpu: 1
          memory: 1Gi

  endpoints:
    - name: a2a
      port: 9000
      public: true

  volumes:
    - name: models
      source: "@LLM_MODELS"
$$
    MIN_INSTANCES = 1
    MAX_INSTANCES = 1;

-- ============================================================================
-- IMPORTANT: The HOTELS_A2A_AGENT_URL and FLIGHTS_A2A_AGENT_URL above use
-- SPCS internal DNS. The format is: http://<service-name>:<port>
-- The internal DNS hostname is the lowercase service name (travel-a2a-agent).
-- If you named your Cortex agents service differently, update accordingly.
-- You can find active service names with: SHOW SERVICES;
-- ============================================================================

-- Step 7: Check service status
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_ORCHESTRATOR');

-- Wait for status to show READY, then get the public endpoint:
SHOW ENDPOINTS IN SERVICE TRAVEL_ORCHESTRATOR;
-- Copy the 'ingress_url' for the 'a2a' endpoint

-- Step 8: View logs
-- LLM server logs:
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'llm-server', 100);

-- External agent logs:
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'external-agent', 100);


-- ============================================================================
-- TESTING
-- ============================================================================
-- Set environment variables in your terminal:
--
--   export INGRESS_URL="<ingress_url from Step 7>"
--   export ACCOUNT_LOCATOR="<your account locator>"
--   export USERNAME="<your username>"
--
-- Then run:
--   python external_agent/test_external_agent.py --query "What is 2+2?"
--   python external_agent/test_external_agent.py --query "Show me 5-star hotels in Paris"
--   python external_agent/test_external_agent.py --query "Find business class flights from JFK to London"


-- ============================================================================
-- SERVICE MANAGEMENT
-- ============================================================================

-- Suspend (stops billing)
-- ALTER SERVICE TRAVEL_ORCHESTRATOR SUSPEND;

-- Resume
-- ALTER SERVICE TRAVEL_ORCHESTRATOR RESUME;

-- Delete everything
-- DROP SERVICE TRAVEL_ORCHESTRATOR;
-- DROP COMPUTE POOL TRAVEL_ORCHESTRATOR_POOL;
