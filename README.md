# TravelDemo Cortex A2A Agent

An Agent-to-Agent (A2A) protocol wrapper for Snowflake Cortex Agents deployed on **Snowpark Container Services (SPCS)**. This demo exposes two domain-specific Cortex Agents — a Hotels Booking Agent and a Flights Booking Agent — through the Google A2A protocol. A Travel Orchestrator service runs a local LLM (Qwen2.5-1.5B via llama.cpp) to classify incoming queries and route them to the appropriate agent automatically.

## Architecture

```
                                               SPCS Service (TRAVEL_ORCHESTRATOR)
┌─────────────────┐  Public Endpoint  ┌─────────────────────────────────────────────────────┐
│   A2A Client    │──────────────────▶│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  (Other Agents) │    (JWT Auth)     │  │ travel-orchestr. │─▶│       llm-server         │ │
└─────────────────┘                   │  │  (Python, :9000) │  │  (llama.cpp, :8080)      │ │
                                      │  │  3-way Router    │  │  Qwen2.5-1.5B (Q4_K_M)  │ │
                                      │  └───┬──────────┬───┘  └──────────────────────────┘ │
                                      └──────┼──────────┼────────────────────────────────────┘
                                   HOTELS:   │          │ FLIGHTS:
                                        (SPCS internal DNS)
                                             │          │
                             SPCS Service (TRAVEL_A2A_AGENT)
                                    ┌────────┘          └────────┐
                                    ▼                            ▼
                    ┌───────────────────────────────────────────────────────┐
                    │  ┌──────────────────────┐  ┌──────────────────────┐   │
                    │  │    hotels-agent       │  │    flights-agent     │   │
                    │  │  (Python, :8000)      │  │  (Python, :8001)     │   │
                    │  │  public endpoint      │  │  internal only       │   │
                    │  └──────────┬────────────┘  └──────────┬───────────┘   │
                    └────────────┼──────────────────────────┼────────────────┘
                                 │    SPCS Session Token    │
                                 └──────────────┬───────────┘
                                                ▼
                                ┌────────────────────────────────┐
                                │     Snowflake Cortex Agent     │
                                │  HOTELS_BOOKING_AGENT  (:8000) │
                                │  FLIGHTS_BOOKING_AGENT (:8001) │
                                └────────────────────────────────┘
```

The orchestrator uses the local LLM to classify each query:
- `HOTELS:` → `hotels-agent` (:8000) — hotel availability, pricing, guest reviews
- `FLIGHTS:` → `flights-agent` (:8001) — fares, routes, schedules, passenger feedback
- General knowledge → answered directly by the local LLM

## A2A Protocol Flow

All three agents expose the [Google A2A protocol](https://github.com/google/a2a) — a standard JSON-RPC interface over HTTPS with JWT authentication. Any A2A-compatible client can discover and call them without custom integration code.

There are two A2A hops in the full request path:

1. **External client → `TRAVEL_ORCHESTRATOR`** (public SPCS endpoint, JWT auth)
   The orchestrator is an **A2A server**. It exposes a `/.well-known/agent-card.json` discovery endpoint describing its capabilities and accepts `message/send` JSON-RPC requests on port 9000.

2. **`TRAVEL_ORCHESTRATOR` → `hotels-agent` or `flights-agent`** (SPCS internal DNS, JWT auth)
   After classifying the query, the orchestrator becomes an **A2A client** and forwards the request to the appropriate domain agent over the internal SPCS network (`http://travel-a2a-agent:8000` or `:8001`).

The domain agents then call the Snowflake Cortex Agent REST API using an SPCS session token — the only non-A2A hop in the chain. This means the orchestrator acts as both an A2A server and an A2A client simultaneously, which is the core agent-to-agent chaining pattern this demo illustrates.

## Repository Structure

```
spcs_cortex_agent_a2a/
├── agents/
│   ├── hotels/             # Hotels Booking A2A agent (port 8000, public)
│   │   ├── executor.py     # Thin subclass of CortexExecutorBase
│   │   ├── main.py         # Hotels agent entrypoint
│   │   ├── Dockerfile      # Builds from repo root (shared/ + agents/hotels/)
│   │   ├── requirements.txt
│   │   └── test_hotels_agent.py # Quick test client for the hotels agent
│   │
│   ├── flights/            # Flights Booking A2A agent (port 8001, internal)
│   │   ├── executor.py     # Thin subclass of CortexExecutorBase
│   │   ├── main.py         # Flights agent entrypoint
│   │   ├── Dockerfile      # Builds from repo root (shared/ + agents/flights/)
│   │   └── requirements.txt
│   │
│   └── orchestrator/       # Travel Orchestrator (port 9000, public)
│       ├── executor.py     # LLM routing logic (HOTELS: / FLIGHTS: prefixes)
│       ├── main.py
│       ├── llm_client.py   # OpenAI-compatible client for local llama.cpp
│       ├── snowflake_a2a_client.py  # A2A client for SPCS-to-SPCS calls
│       ├── Dockerfile      # Builds from repo root (shared/ + agents/orchestrator/)
│       ├── requirements.txt
│       └── test_travel_orchestrator.py
│
├── shared/                 # Shared utilities used by all agents
│   ├── auth.py             # JWT generation + SPCS session token helper
│   ├── cortex_executor_base.py  # Base A2A executor that calls Cortex Agent REST API
│   └── response_cleaner.py # Dedup and chain-of-thought removal for Cortex responses
│
└── setup/
    ├── SNOWFLAKE_SETUP.sql         # One-time Snowflake data setup
    ├── DEPLOY_SPCS.sql             # All SPCS services (TRAVEL_A2A_AGENT + TRAVEL_ORCHESTRATOR)
    ├── hotels_semantic.yaml        # Cortex Analyst semantic model for HOTELS
    └── flights_semantic.yaml       # Cortex Analyst semantic model for FLIGHTS
```

## Prerequisites

- Python 3.11+
- Docker
- Snowflake account (trial accounts do not support SPCS)
- A warehouse named `COMPUTE_WH` (used by Cortex Search services and Cortex Agents)
- SnowCLI installed with a configured connection — https://docs.snowflake.com/en/developer-guide/snowflake-cli/connecting/connect

## Data Model

All demo data lives in `TRAVEL_DEMO.AGENTS`:

| Table | Description |
|-------|-------------|
| `HOTELS` | Hotel inventory — pricing, availability, ratings, amenities |
| `HOTEL_REVIEWS` | Guest reviews (searched by `HOTEL_REVIEWS_SEARCH`) |
| `FLIGHTS` | Flight inventory — fares, routes, schedules, seat classes |
| `FLIGHT_FEEDBACK` | Passenger feedback (searched by `FLIGHT_FEEDBACK_SEARCH`) |

Two Cortex Agents are created in the same schema:

| Agent | Tools |
|-------|-------|
| `HOTELS_BOOKING_AGENT` | `cortex_analyst` (hotels_semantic.yaml) + `cortex_search` (HOTEL_REVIEWS_SEARCH) |
| `FLIGHTS_BOOKING_AGENT` | `cortex_analyst` (flights_semantic.yaml) + `cortex_search` (FLIGHT_FEEDBACK_SEARCH) |

---

## Step 1 — Set Up Snowflake Data

```bash
# Run the setup script in Snowflake (Snowsight or SnowCLI)
snow sql -f setup/SNOWFLAKE_SETUP.sql --connection $SNOW_CONNECTION

# Upload semantic model YAMLs to the stage
snow stage copy setup/hotels_semantic.yaml  @TRAVEL_DEMO.AGENTS.SEMANTIC_MODELS --connection $SNOW_CONNECTION
snow stage copy setup/flights_semantic.yaml @TRAVEL_DEMO.AGENTS.SEMANTIC_MODELS --connection $SNOW_CONNECTION

# Verify
snow sql -q "LIST @TRAVEL_DEMO.AGENTS.SEMANTIC_MODELS;" --connection $SNOW_CONNECTION
snow sql -q "SHOW AGENTS IN SCHEMA TRAVEL_DEMO.AGENTS;" --connection $SNOW_CONNECTION
```

---

## Step 2 — Generate RSA Key Pair (if needed)

```bash
# Generate private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt

# Generate public key
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub

# Get the public key content (for Snowflake)
grep -v "BEGIN\|END" rsa_key.pub | tr -d '\n'
```

Register the public key with your Snowflake user:

```sql
ALTER USER your_username SET RSA_PUBLIC_KEY='MIIBIjAN...your_public_key...AQAB';
DESC USER your_username;  -- Look for RSA_PUBLIC_KEY_FP
```

---

## Step 3 — Create SPCS Infrastructure

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE TRAVEL_DEMO;
USE SCHEMA AGENTS;

-- Compute pool for the Cortex agents service
CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_AGENT_POOL
    MIN_NODES = 1 MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_XS
    AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 1800;

-- Compute pool for the Travel Orchestrator (needs more RAM for local LLM)
CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_ORCHESTRATOR_POOL
    MIN_NODES = 1 MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_S
    AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 1800;

-- Image repository
CREATE IMAGE REPOSITORY IF NOT EXISTS A2A_IMAGES;

-- Get repository URL (needed for docker push)
SHOW IMAGE REPOSITORIES LIKE 'A2A_IMAGES';
```

---

## Step 4 — Build and Push Docker Images

```bash
export REPO_URL="<repository_url>"       # from SHOW IMAGE REPOSITORIES
export SNOW_CONNECTION="<YOUR_CONNECTION>"

# Login to Snowflake registry
snow spcs image-registry login --connection $SNOW_CONNECTION

# Hotels agent (build from repo root)
docker build --platform linux/amd64 -f agents/hotels/Dockerfile -t hotels-agent:latest .
docker tag hotels-agent:latest $REPO_URL/hotels-agent:latest
docker push $REPO_URL/hotels-agent:latest

# Flights agent (build from repo root)
docker build --platform linux/amd64 -f agents/flights/Dockerfile -t flights-agent:latest .
docker tag flights-agent:latest $REPO_URL/flights-agent:latest
docker push $REPO_URL/flights-agent:latest

# Travel Orchestrator (build from repo root)
docker build --platform linux/amd64 -f agents/orchestrator/Dockerfile -t travel-orchestrator-agent:latest .
docker tag travel-orchestrator-agent:latest $REPO_URL/travel-orchestrator-agent:latest
docker push $REPO_URL/travel-orchestrator-agent:latest

# llama.cpp server image
docker pull --platform linux/amd64 ghcr.io/ggml-org/llama.cpp:server
docker tag ghcr.io/ggml-org/llama.cpp:server $REPO_URL/llama-cpp-server:latest
docker push $REPO_URL/llama-cpp-server:latest
```

---

## Step 5 — Deploy the TRAVEL_A2A_AGENT Service

See `setup/DEPLOY_SPCS.sql` for the full SQL (database and schema are hardcoded to `TRAVEL_DEMO.AGENTS`):

```sql
CREATE SERVICE TRAVEL_A2A_AGENT
    IN COMPUTE POOL TRAVEL_AGENT_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: hotels-agent
      image: /TRAVEL_DEMO/AGENTS/A2A_IMAGES/hotels-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: AGENTS
        AGENT_NAME: HOTELS_BOOKING_AGENT
    - name: flights-agent
      image: /TRAVEL_DEMO/AGENTS/A2A_IMAGES/flights-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: AGENTS
        AGENT_NAME: FLIGHTS_BOOKING_AGENT
        SPCS_SERVICE_URL: "http://travel-a2a-agent:8001"
  endpoints:
    - name: a2a
      port: 8000
      public: true
    - name: flights-api
      port: 8001
      public: false
$$
    MIN_INSTANCES = 1 MAX_INSTANCES = 1;
```

Verify both containers are running:

```sql
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_A2A_AGENT');
SHOW ENDPOINTS IN SERVICE TRAVEL_A2A_AGENT;
```

---

## Step 6 — Upload the LLM Model to Snowflake

Run the stored procedure to download the Qwen2.5-1.5B-Instruct GGUF model (~1GB) directly from HuggingFace into `@LLM_MODELS` — no local download required:

```bash
snow sql -c $SNOW_CONNECTION -q "CALL TRAVEL_DEMO.AGENTS.DOWNLOAD_LLM_MODEL();"
```

Or from Snowsight:

```sql
CALL TRAVEL_DEMO.AGENTS.DOWNLOAD_LLM_MODEL();
```

Verify the upload completed:

```bash
snow sql -c $SNOW_CONNECTION -q "LIST @TRAVEL_DEMO.AGENTS.LLM_MODELS;"
```

---

## Step 7 — Deploy the TRAVEL_ORCHESTRATOR Service

See `setup/DEPLOY_SPCS.sql` for the full SQL. Key points:
- Uses `TRAVEL_ORCHESTRATOR_POOL` (CPU_X64_S — 2 vCPU, 8 GB RAM)
- Two-container service: llm-server (port 8080) + travel-orchestrator (port 9000)
- Routes to `TRAVEL_A2A_AGENT` via internal DNS

Verify:

```sql
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_ORCHESTRATOR');
SHOW ENDPOINTS IN SERVICE TRAVEL_ORCHESTRATOR;
```

---

## Usage & Testing

### Calling the Hotels Agent Directly

The `TRAVEL_A2A_AGENT` public endpoint (port 8000) requires Snowflake JWT authentication.

#### Set Environment Variables

```bash
export INGRESS_URL="<ingress_url>"           # from SHOW ENDPOINTS
export ACCOUNT_LOCATOR="<account_locator>"   # SELECT CURRENT_ACCOUNT();
export USERNAME="<username>"                 # SELECT CURRENT_USER();
```

#### Generate JWT Token

```bash
TOKEN=$(python3 -c "
import sys; sys.path.insert(0, 'shared')
from auth import generate_snowflake_jwt
print(generate_snowflake_jwt('$ACCOUNT_LOCATOR', '$USERNAME', 'rsa_key.p8'))
")
```

#### Discovery Endpoint

Returns the agent's capabilities, description, and supported methods — the standard A2A discovery mechanism. Any A2A-compatible client should call this first.

```bash
curl -H "Authorization: Snowflake Token=\"$TOKEN\"" \
  https://$INGRESS_URL/.well-known/agent-card.json
```

#### Send a Query

```bash
curl -X POST https://$INGRESS_URL/ \
  -H "Authorization: Snowflake Token=\"$TOKEN\"" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "user",
        "parts": [{"type": "text", "text": "Show me available 5-star hotels in Paris"}]
      }
    }
  }'
```

#### Test Client

```bash
python agents/hotels/test_hotels_agent.py --query "List hotels with free cancellation in Tokyo"
python agents/hotels/test_hotels_agent.py --card-only
```

### Using the Travel Orchestrator

The `TRAVEL_ORCHESTRATOR` public endpoint (port 9000) classifies and routes queries automatically.

```bash
export INGRESS_URL="<ingress_url>"           # from SHOW ENDPOINTS IN SERVICE TRAVEL_ORCHESTRATOR
export ACCOUNT_LOCATOR="<org_name>-<account_locator>"
export USERNAME="<username>"

# General knowledge — answered by local LLM
python agents/orchestrator/test_travel_orchestrator.py --query "What is 2+2?"

# Hotel question — routed to Hotels Booking Agent
python agents/orchestrator/test_travel_orchestrator.py --query "Show me 5-star hotels in Paris under $600/night"

# Flight question — routed to Flights Booking Agent
python agents/orchestrator/test_travel_orchestrator.py --query "Find business class flights from JFK to London"
```

---

## Service Management

```sql
-- View logs
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT',    0, 'hotels-agent',        100);
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT',    0, 'flights-agent',       100);
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'llm-server',          100);
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'travel-orchestrator', 100);

-- Suspend (stops billing)
ALTER SERVICE TRAVEL_A2A_AGENT SUSPEND;
ALTER SERVICE TRAVEL_ORCHESTRATOR SUSPEND;

-- Resume
ALTER SERVICE TRAVEL_A2A_AGENT RESUME;
ALTER SERVICE TRAVEL_ORCHESTRATOR RESUME;

-- Delete
DROP SERVICE TRAVEL_A2A_AGENT;
DROP SERVICE TRAVEL_ORCHESTRATOR;
DROP COMPUTE POOL TRAVEL_AGENT_POOL;
DROP COMPUTE POOL TRAVEL_ORCHESTRATOR_POOL;
```

---

## Resources
- [Snowflake Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Snowpark Container Services](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/overview)
- [Snowflake Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- [Snowflake Cortex Search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview)
- [Snowflake Key-Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)
