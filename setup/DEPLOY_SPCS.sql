-- ============================================================================
-- DEPLOY_SPCS.sql — Deploy all SPCS services for the TravelDemo A2A demo
--
-- This file deploys two SPCS services:
--
--   Service 1: TRAVEL_A2A_AGENT
--     - hotels-agent:  Hotels Booking A2A agent  (port 8000, public endpoint)
--     - flights-agent: Flights Booking A2A agent (port 8001, internal only)
--
--   Service 2: TRAVEL_ORCHESTRATOR
--     - llm-server:         llama.cpp serving Qwen2.5-1.5B (port 8080)
--     - travel-orchestrator: Python A2A server that routes queries (port 9000)
--
-- Prerequisites:
--   - Run setup/SNOWFLAKE_SETUP.sql first (database, tables, search services,
--     Cortex Agents, SEMANTIC_MODELS stage)
--   - Upload semantic YAMLs to @SEMANTIC_MODELS (see SNOWFLAKE_SETUP.sql)
--   - Build and push Docker images (see instructions below)
--   - For the orchestrator: run CALL TRAVEL_DEMO.AGENTS.DOWNLOAD_LLM_MODEL(); to upload GGUF model
--
-- Replace this placeholder before running:
--   <REPO_URL>        — Image repository URL (from SHOW IMAGE REPOSITORIES)
-- Database and schema are hardcoded to TRAVEL_DEMO.AGENTS.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE TRAVEL_DEMO;
USE SCHEMA AGENTS;

-- ============================================================================
-- 1. SHARED SPCS INFRASTRUCTURE
-- ============================================================================

-- Image repository (shared by all services)
CREATE IMAGE REPOSITORY IF NOT EXISTS A2A_IMAGES;

-- Get repository URL (needed for docker push)
SHOW IMAGE REPOSITORIES LIKE 'A2A_IMAGES';
-- Copy the 'repository_url' value — you'll need it for docker push

-- Stage for the local LLM model (used by the orchestrator)
CREATE STAGE IF NOT EXISTS LLM_MODELS
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- ============================================================================
-- 2. DOCKER BUILD INSTRUCTIONS
--
-- Run these commands from your terminal (not in Snowflake):
--
--   export REPO_URL="<repository_url>"       # from SHOW IMAGE REPOSITORIES
--   export SNOW_CONNECTION="<YOUR_CONNECTION>"
--
--   # Login to Snowflake registry
--   snow spcs image-registry login --connection $SNOW_CONNECTION
--
--   # Hotels agent (build from repo root)
--   docker build --platform linux/amd64 -f agents/hotels/Dockerfile -t hotels-agent:latest .
--   docker tag hotels-agent:latest $REPO_URL/hotels-agent:latest
--   docker push $REPO_URL/hotels-agent:latest
--
--   # Flights agent (build from repo root)
--   docker build --platform linux/amd64 -f agents/flights/Dockerfile -t flights-agent:latest .
--   docker tag flights-agent:latest $REPO_URL/flights-agent:latest
--   docker push $REPO_URL/flights-agent:latest
--
--   # Travel orchestrator (build from repo root)
--   docker build --platform linux/amd64 -f agents/orchestrator/Dockerfile -t travel-orchestrator-agent:latest .
--   docker tag travel-orchestrator-agent:latest $REPO_URL/travel-orchestrator-agent:latest
--   docker push $REPO_URL/travel-orchestrator-agent:latest
--
--   # llama.cpp server (pull from GHCR, re-tag, push to SPCS registry)
--   docker pull --platform linux/amd64 ghcr.io/ggml-org/llama.cpp:server
--   docker tag ghcr.io/ggml-org/llama.cpp:server $REPO_URL/llama-cpp-server:latest
--   docker push $REPO_URL/llama-cpp-server:latest
-- ============================================================================

-- ============================================================================
-- 3. SERVICE 1: TRAVEL_A2A_AGENT (Hotels + Flights)
--
-- Two containers sharing a compute pool:
--   - hotels-agent  wraps HOTELS_BOOKING_AGENT  (port 8000, public)
--   - flights-agent wraps FLIGHTS_BOOKING_AGENT (port 8001, internal)
-- ============================================================================

CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_POOL
    MIN_NODES = 1
    MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_S
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 1800;

CREATE SERVICE TRAVEL_A2A_AGENT
    IN COMPUTE POOL TRAVEL_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: hotels-agent
      image: /TRAVEL_DEMO/AGENTS/A2A_IMAGES/hotels-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: AGENTS
        AGENT_NAME: HOTELS_BOOKING_AGENT
        AGENT_DESCRIPTION: "Senior Hotel Concierge answering questions about hotel availability, pricing, amenities, and guest reviews."
      resources:
        requests:
          cpu: 0.5
          memory: 512Mi
        limits:
          cpu: 1
          memory: 1Gi

    - name: flights-agent
      image: /TRAVEL_DEMO/AGENTS/A2A_IMAGES/flights-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: AGENTS
        AGENT_NAME: FLIGHTS_BOOKING_AGENT
        AGENT_DESCRIPTION: "Senior Flight Booking Specialist answering questions about flight availability, fares, schedules, and passenger feedback."
      resources:
        requests:
          cpu: 0.5
          memory: 512Mi
        limits:
          cpu: 1
          memory: 1Gi

  endpoints:
    - name: a2a
      port: 8000
      public: true
    - name: flights-api
      port: 8001
      public: false
      # Port 8001 is declared as a non-public endpoint so SPCS routes
      # inter-service traffic (from TRAVEL_ORCHESTRATOR) to the flights-agent.
$$
    MIN_INSTANCES = 1
    MAX_INSTANCES = 1;

-- Verify TRAVEL_A2A_AGENT
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_A2A_AGENT');
SHOW ENDPOINTS IN SERVICE TRAVEL_A2A_AGENT;

-- ============================================================================
-- 4. SERVICE 2: TRAVEL_ORCHESTRATOR
--
-- Two containers sharing a compute pool:
--   - llm-server:         llama.cpp serving Qwen2.5-1.5B via @LLM_MODELS stage
--   - travel-orchestrator: classifies queries and routes to TRAVEL_A2A_AGENT
--
-- The orchestrator routes:
--   HOTELS:  questions → hotels-agent  (http://travel-a2a-agent:8000)
--   FLIGHTS: questions → flights-agent (http://travel-a2a-agent:8001)
--   General questions  → answered directly by the local LLM
--
-- Prerequisites:
--   - TRAVEL_A2A_AGENT must be deployed and running (see above)
--   - Upload the GGUF model (runs inside Snowflake, no local download needed):
--       CALL TRAVEL_DEMO.AGENTS.DOWNLOAD_LLM_MODEL();

-- Verify model is uploaded before proceeding:
-- LIST @TRAVEL_DEMO.AGENTS.LLM_MODELS;
-- You should see: qwen2.5-1.5b-instruct-q4_k_m.gguf

CREATE SERVICE TRAVEL_ORCHESTRATOR
    IN COMPUTE POOL TRAVEL_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: llm-server
      image: /TRAVEL_DEMO/AGENTS/A2A_IMAGES/llama-cpp-server:latest
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
        port: 8080
        path: /health

    - name: travel-orchestrator
      image: /TRAVEL_DEMO/AGENTS/A2A_IMAGES/travel-orchestrator-agent:latest
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
      source: "@TRAVEL_DEMO.AGENTS.LLM_MODELS"
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

-- Verify TRAVEL_ORCHESTRATOR
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_ORCHESTRATOR');
SHOW ENDPOINTS IN SERVICE TRAVEL_ORCHESTRATOR;

-- ============================================================================
-- 5. VIEW LOGS
-- ============================================================================

-- TRAVEL_A2A_AGENT
-- SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'hotels-agent',  100);
-- SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'flights-agent', 100);

-- TRAVEL_ORCHESTRATOR
-- SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'llm-server',          100);
-- SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'travel-orchestrator',  100);

-- ============================================================================
-- 6. UPDATING EXISTING SERVICES
-- ============================================================================

-- If TRAVEL_A2A_AGENT already exists, use ALTER SERVICE instead of CREATE:
-- ALTER SERVICE TRAVEL_A2A_AGENT FROM SPECIFICATION $$ ... $$;

-- If TRAVEL_ORCHESTRATOR already exists:
-- ALTER SERVICE TRAVEL_ORCHESTRATOR FROM SPECIFICATION $$ ... $$;

-- ============================================================================
-- 7. SERVICE MANAGEMENT
-- ============================================================================

-- Suspend (stops billing)
-- ALTER SERVICE TRAVEL_A2A_AGENT SUSPEND;
-- ALTER SERVICE TRAVEL_ORCHESTRATOR SUSPEND;

-- Resume
-- ALTER SERVICE TRAVEL_A2A_AGENT RESUME;
-- ALTER SERVICE TRAVEL_ORCHESTRATOR RESUME;

-- Delete everything
-- DROP SERVICE TRAVEL_A2A_AGENT;
-- DROP SERVICE TRAVEL_ORCHESTRATOR;
-- DROP COMPUTE POOL TRAVEL_POOL;
