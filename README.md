# TravelDemo Cortex A2A Agent

An Agent-to-Agent (A2A) protocol wrapper for Snowflake Cortex Agents deployed on **Snowpark Container Services (SPCS)**. This demo exposes two domain-specific Cortex Agents — a Hotels Booking Agent and a Flights Booking Agent — through the Google A2A protocol, with a local-LLM orchestrator that routes incoming questions automatically.

## Architecture

```
┌─────────────────┐  Public Endpoint  ┌──────────────────────┐  SPCS Session Token  ┌──────────────────────────┐
│   A2A Client    │──────────────────▶│   A2A Wrapper        │─────────────────────▶│  Snowflake Cortex Agent  │
│  (Other Agents) │    (JWT Auth)     │   (SPCS Service)     │                      │  (Hotels or Flights)     │
└─────────────────┘                   └──────────────────────┘                      └──────────────────────────┘
```

The A2A client connects to the A2A wrapper via a **public SPCS endpoint** using JWT authentication. The wrapper uses the **SPCS session token** to authenticate with the Snowflake Cortex Agent on the internal network.

## Repository Structure

```
spcs_cortex_agent_a2a/
├── executor.py             # Hotels Booking A2A agent executor (port 8000)
├── main.py                 # Hotels Booking A2A agent entrypoint
├── auth.py                 # JWT + SPCS token auth helper
├── Dockerfile              # Hotels agent container image
├── requirements.txt
├── test_a2a.py             # Quick test client for the hotels agent
│
├── flights_agent/          # Flights Booking A2A agent (port 8001, internal)
│   ├── executor.py
│   ├── main.py
│   ├── auth.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── DEPLOY.sql          # SPCS service spec for TRAVEL_A2A_AGENT
│
├── external_agent/         # Travel Orchestrator (port 9000, public)
│   ├── executor.py         # LLM routing logic (HOTELS: / FLIGHTS: prefixes)
│   ├── main.py
│   ├── llm_client.py
│   ├── snowflake_a2a_client.py
│   ├── Dockerfile
│   ├── download_model.sh
│   ├── test_external_agent.py
│   └── DEPLOY.sql          # SPCS service spec for TRAVEL_ORCHESTRATOR
│
└── setup/
    ├── SNOWFLAKE_SETUP.sql         # One-time Snowflake data setup
    ├── hotels_semantic.yaml        # Cortex Analyst semantic model for HOTELS
    └── flights_semantic.yaml       # Cortex Analyst semantic model for FLIGHTS
```

## Prerequisites

- Python 3.11+
- Docker
- Snowflake account (trial accounts do not support SPCS)
- SnowCLI installed with a configured connection — https://docs.snowflake.com/en/developer-guide/snowflake-cli/connecting/connect

## Data Model

All demo data lives in `TRAVEL_DEMO.BOOKING`:

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
snow stage copy setup/hotels_semantic.yaml  @TRAVEL_DEMO.BOOKING.BOOKING_MODELS --connection $SNOW_CONNECTION
snow stage copy setup/flights_semantic.yaml @TRAVEL_DEMO.BOOKING.BOOKING_MODELS --connection $SNOW_CONNECTION

# Verify
snow sql -q "LIST @TRAVEL_DEMO.BOOKING.BOOKING_MODELS;" --connection $SNOW_CONNECTION
snow sql -q "SHOW AGENTS IN SCHEMA TRAVEL_DEMO.BOOKING;" --connection $SNOW_CONNECTION
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
USE SCHEMA BOOKING;

-- Compute pool for the Cortex agents service
CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_AGENT_POOL
    MIN_NODES = 1 MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_XS
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

# Hotels agent (root directory)
docker build --platform linux/amd64 -t cortex-hotels-agent:latest .
docker tag cortex-hotels-agent:latest $REPO_URL/cortex-hotels-agent:latest
docker push $REPO_URL/cortex-hotels-agent:latest

# Flights agent
cd flights_agent
docker build --platform linux/amd64 -t cortex-flights-agent:latest .
docker tag cortex-flights-agent:latest $REPO_URL/cortex-flights-agent:latest
docker push $REPO_URL/cortex-flights-agent:latest
cd ..
```

---

## Step 5 — Deploy the TRAVEL_A2A_AGENT Service

See `flights_agent/DEPLOY.sql` for the full SQL, replacing `<AGENT_DATABASE>` and `<AGENT_SCHEMA>`:

```sql
CREATE SERVICE TRAVEL_A2A_AGENT
    IN COMPUTE POOL TRAVEL_AGENT_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: hotels-agent
      image: /TRAVEL_DEMO/BOOKING/A2A_IMAGES/cortex-hotels-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: BOOKING
        AGENT_NAME: HOTELS_BOOKING_AGENT
    - name: flights-agent
      image: /TRAVEL_DEMO/BOOKING/A2A_IMAGES/cortex-flights-agent:latest
      env:
        AGENT_DATABASE: TRAVEL_DEMO
        AGENT_SCHEMA: BOOKING
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

## Calling the Hotels Agent Directly

The SPCS public endpoint (port 8000) requires Snowflake JWT authentication.

### Set Environment Variables

```bash
export INGRESS_URL="<ingress_url>"           # from SHOW ENDPOINTS
export ACCOUNT_LOCATOR="<account_locator>"   # SELECT CURRENT_ACCOUNT();
export USERNAME="<username>"                 # SELECT CURRENT_USER();
```

### Generate JWT Token

```bash
TOKEN=$(python3 -c "
from auth import generate_snowflake_jwt
print(generate_snowflake_jwt('$ACCOUNT_LOCATOR', '$USERNAME', 'rsa_key.p8'))
")
```

### Discovery Endpoint

```bash
curl -H "Authorization: Snowflake Token=\"$TOKEN\"" \
  https://$INGRESS_URL/.well-known/agent-card.json
```

### Send a Query

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

### Test Client

```bash
python test_a2a.py --query "List hotels with free cancellation in Tokyo"
python test_a2a.py --card-only
```

---

## Service Management

```sql
-- View logs
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'hotels-agent',  100);
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_A2A_AGENT', 0, 'flights-agent', 100);

-- Suspend (stops billing)
ALTER SERVICE TRAVEL_A2A_AGENT SUSPEND;

-- Resume
ALTER SERVICE TRAVEL_A2A_AGENT RESUME;

-- Delete
DROP SERVICE TRAVEL_A2A_AGENT;
DROP COMPUTE POOL TRAVEL_AGENT_POOL;
```

---

# Travel Orchestrator

The `external_agent/` directory contains the Travel Orchestrator — a second SPCS service that runs a local LLM (Qwen2.5-1.5B via llama.cpp) to classify incoming queries and routes them to the appropriate Cortex agent via SPCS internal DNS.

## Architecture

```
[Model Deployment – one-time setup]

┌──────────────┐  download_model.sh  ┌──────────────────┐  SPCS volume  ┌───────────────────┐
│  HuggingFace │────────────────────▶│ Snowflake Stage  │──────────────▶│    llm-server     │
│ (Qwen GGUF)  │                     │  (@LLM_MODELS)   │    mount      │  (loads at start) │
└──────────────┘                     └──────────────────┘               └───────────────────┘

[Runtime]

                                               SPCS Service (TRAVEL_ORCHESTRATOR)
┌─────────────────┐  Public Endpoint  ┌─────────────────────────────────────────────────────┐
│   A2A Client    │──────────────────▶│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  (Other Agents) │    (JWT Auth)     │  │  external-agent  │─▶│       llm-server         │ │
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

## Prerequisites

- **TRAVEL_A2A_AGENT** service must be deployed and running (see above)
- Docker
- SnowCLI

## Deployment

### Step 1: Download and Upload the LLM Model

```bash
cd external_agent
./download_model.sh <SNOW_CONNECTION> <AGENT_DATABASE> <AGENT_SCHEMA>
```

This downloads the Qwen2.5-1.5B-Instruct GGUF model (~1GB) and uploads it to `@LLM_MODELS`.

### Step 2: Build and Push the Docker Image

```bash
export REPO_URL="<repository_url>"
export SNOW_CONNECTION="<YOUR_CONNECTION>"

cd external_agent
docker build --platform linux/amd64 -t external-a2a-agent:latest .
snow spcs image-registry login --connection $SNOW_CONNECTION
docker tag external-a2a-agent:latest $REPO_URL/external-a2a-agent:latest
docker push $REPO_URL/external-a2a-agent:latest
```

You also need to push the llama.cpp server image to the SPCS registry:

```bash
docker pull --platform linux/amd64 ghcr.io/ggml-org/llama.cpp:server
docker tag ghcr.io/ggml-org/llama.cpp:server $REPO_URL/llama-cpp-server:latest
docker push $REPO_URL/llama-cpp-server:latest
```

### Step 3: Deploy the Service

See `external_agent/DEPLOY.sql` for the full SQL. Key points:
- Creates `TRAVEL_ORCHESTRATOR_POOL` (CPU_X64_S — 2 vCPU, 8 GB RAM)
- Two-container service: llm-server (port 8080) + external-agent (port 9000)
- Routes to `TRAVEL_A2A_AGENT` via internal DNS

```sql
CREATE COMPUTE POOL IF NOT EXISTS TRAVEL_ORCHESTRATOR_POOL
    MIN_NODES = 1 MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_S
    AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 1800;
```

### Step 4: Verify and Test

```sql
SELECT SYSTEM$GET_SERVICE_STATUS('TRAVEL_ORCHESTRATOR');
SHOW ENDPOINTS IN SERVICE TRAVEL_ORCHESTRATOR;
```

```bash
export INGRESS_URL="<ingress_url>"
export ACCOUNT_LOCATOR="<org_name>-<account_locator>"
export USERNAME="<username>"

# General knowledge — answered by local LLM
python external_agent/test_external_agent.py --query "What is 2+2?"

# Hotel question — routed to Hotels Booking Agent
python external_agent/test_external_agent.py --query "Show me 5-star hotels in Paris under $600/night"

# Flight question — routed to Flights Booking Agent
python external_agent/test_external_agent.py --query "Find business class flights from JFK to London"
```

## Service Management

```sql
-- View logs
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'llm-server',     100);
SELECT SYSTEM$GET_SERVICE_LOGS('TRAVEL_ORCHESTRATOR', 0, 'external-agent', 100);

-- Suspend / Resume / Delete
ALTER SERVICE TRAVEL_ORCHESTRATOR SUSPEND;
ALTER SERVICE TRAVEL_ORCHESTRATOR RESUME;
DROP SERVICE TRAVEL_ORCHESTRATOR;
DROP COMPUTE POOL TRAVEL_ORCHESTRATOR_POOL;
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Service not starting | Compute pool not ready | Wait for `DESCRIBE COMPUTE POOL` to show ACTIVE/IDLE |
| 401 Unauthorized | Invalid/expired token | Regenerate JWT token (expires after 1 hour) |
| Internal error | Missing SNOWFLAKE_HOST | Do not set SNOWFLAKE_HOST manually — let SPCS provide it |
| Agent not found (404) | Wrong agent path | Verify with `SHOW AGENTS IN SCHEMA TRAVEL_DEMO.BOOKING;` |
| Hotels agent unreachable | Wrong service name in DNS | Internal DNS uses lowercase service name (`travel-a2a-agent`) |
| Flights agent unreachable | Port 8001 not declared | Ensure `flights-api` endpoint is declared in service spec |

---

## Resources

- [A2A Protocol](https://github.com/google/a2a)
- [Snowflake Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Snowpark Container Services](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/overview)
- [Snowflake Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- [Snowflake Cortex Search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview)
- [Snowflake Key-Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)
