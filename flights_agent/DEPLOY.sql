-- ============================================================================
-- DEPLOY.sql — Deploy the Hotels & Flights Booking Agents on SPCS
--
-- This file deploys the TRAVEL_A2A_AGENT service, which runs two containers:
--   1. hotels-agent:  Hotels Booking A2A agent  (port 8000, public endpoint)
--   2. flights-agent: Flights Booking A2A agent (port 8001, internal only)
--
-- The Hotels Booking Agent wraps TRAVEL_DEMO.BOOKING.HOTELS_BOOKING_AGENT.
-- The Flights Booking Agent wraps TRAVEL_DEMO.BOOKING.FLIGHTS_BOOKING_AGENT.
--
-- Prerequisites:
--   - Run setup/SNOWFLAKE_SETUP.sql to create the database, tables, search
--     services, and Cortex Agents (HOTELS_BOOKING_AGENT, FLIGHTS_BOOKING_AGENT)
--   - Upload semantic YAMLs to stage (see SNOWFLAKE_SETUP.sql instructions)
--   - Build and push both Docker images to the SPCS image registry
--
-- Replace these placeholders before running:
--   <AGENT_DATABASE>  — e.g. TRAVEL_DEMO
--   <AGENT_SCHEMA>    — e.g. BOOKING
--   <REPO_URL>        — Image repository URL (from SHOW IMAGE REPOSITORIES)
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE <AGENT_DATABASE>;
USE SCHEMA <AGENT_SCHEMA>;

-- ============================================================================
-- Step 1: Build and push Docker images
-- Run these commands from your terminal:
--
--   export REPO_URL="<repository_url>"
--   export SNOW_CONNECTION="<YOUR_CONNECTION>"
--
--   # Build and push the hotels agent image (root directory)
--   docker build --platform linux/amd64 -t cortex-hotels-agent:latest .
--   snow spcs image-registry login --connection $SNOW_CONNECTION
--   docker tag cortex-hotels-agent:latest $REPO_URL/cortex-hotels-agent:latest
--   docker push $REPO_URL/cortex-hotels-agent:latest
--
--   # Build and push the flights agent image
--   cd flights_agent
--   docker build --platform linux/amd64 -t cortex-flights-agent:latest .
--   docker tag cortex-flights-agent:latest $REPO_URL/cortex-flights-agent:latest
--   docker push $REPO_URL/cortex-flights-agent:latest
-- ============================================================================

-- Step 2: Create compute pool
CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_AGENT_POOL
    MIN_NODES = 1
    MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_XS
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 1800;

-- Step 3: Create image repository (if not already created)
CREATE IMAGE REPOSITORY IF NOT EXISTS A2A_IMAGES;

-- Get repository URL
SHOW IMAGE REPOSITORIES LIKE 'A2A_IMAGES';

-- Step 4: Create the TRAVEL_A2A_AGENT service with both containers
CREATE SERVICE TRAVEL_A2A_AGENT
    IN COMPUTE POOL TRAVEL_AGENT_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: hotels-agent
      image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-hotels-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: BOOKING
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
      image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-flights-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: BOOKING
        AGENT_NAME: FLIGHTS_BOOKING_AGENT
        AGENT_DESCRIPTION: "Senior Flight Booking Specialist answering questions about flight availability, fares, schedules, and passenger feedback."
        SPCS_SERVICE_URL: "http://travel-a2a-agent:8001"
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

-- Step 5: Verify both containers are running
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_A2A_AGENT');

-- Step 6: Check logs for each container
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'hotels-agent',  50);
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'flights-agent', 50);

-- Step 7: Get the public endpoint for the hotels agent
SHOW ENDPOINTS IN SERVICE TRAVEL_A2A_AGENT;
-- Copy the 'ingress_url' for the 'a2a' endpoint (port 8000)

-- ============================================================================
-- UPDATING AN EXISTING SERVICE
-- If TRAVEL_A2A_AGENT already exists, use ALTER SERVICE instead of CREATE:
-- ============================================================================

-- ALTER SERVICE TRAVEL_A2A_AGENT FROM SPECIFICATION $$
-- spec:
--   containers:
--     - name: hotels-agent
--       image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-hotels-agent:latest
--       env:
--         AGENT_DATABASE: TRAVEL_DEMO
--         AGENT_SCHEMA:   BOOKING
--         AGENT_NAME:     HOTELS_BOOKING_AGENT
--         AGENT_DESCRIPTION: "Senior Hotel Concierge answering questions about hotel availability, pricing, amenities, and guest reviews."
--       resources:
--         requests: { cpu: 0.5, memory: 512Mi }
--         limits:   { cpu: 1,   memory: 1Gi  }
--
--     - name: flights-agent
--       image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-flights-agent:latest
--       env:
--         AGENT_DATABASE:    TRAVEL_DEMO
--         AGENT_SCHEMA:      BOOKING
--         AGENT_NAME:        FLIGHTS_BOOKING_AGENT
--         AGENT_DESCRIPTION: "Senior Flight Booking Specialist answering questions about flight availability, fares, schedules, and passenger feedback."
--         SPCS_SERVICE_URL:  "http://travel-a2a-agent:8001"
--       resources:
--         requests: { cpu: 0.5, memory: 512Mi }
--         limits:   { cpu: 1,   memory: 1Gi  }
--
--   endpoints:
--     - name: a2a
--       port: 8000
--       public: true
--     - name: flights-api
--       port: 8001
--       public: false
-- $$;

-- ============================================================================
-- SERVICE MANAGEMENT
-- ============================================================================

-- View logs
-- SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'hotels-agent',  100);
-- SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'flights-agent', 100);

-- Suspend (stops billing)
-- ALTER SERVICE TRAVEL_A2A_AGENT SUSPEND;

-- Resume
-- ALTER SERVICE TRAVEL_A2A_AGENT RESUME;

-- Delete
-- DROP SERVICE TRAVEL_A2A_AGENT;
-- DROP COMPUTE POOL TRAVEL_AGENT_POOL;
