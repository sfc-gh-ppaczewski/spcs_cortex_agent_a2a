# Snowflake Cortex A2A Agent

An Agent-to-Agent (A2A) protocol wrapper for Snowflake Cortex Agents deployed on **Snowpark Container Services (SPCS)**. This service exposes your Cortex Agent through the Google A2A protocol, enabling other AI agents to interact with it through a standardized interface.

## Architecture

```
┌─────────────────┐  Public Endpoint  ┌──────────────────────┐  SPCS Session Token  ┌─────────────────────┐
│   A2A Client    │──────────────────▶│   A2A Wrapper        │─────────────────────▶│  Snowflake Cortex   │
│  (Other Agents) │    (JWT Auth)     │   (SPCS Service)     │                      │      Agent          │
└─────────────────┘                   └──────────────────────┘                      └─────────────────────┘
```

The A2A client connects to the A2A wrapper via a **public SPCS endpoint** using JWT authentication. The A2A wrapper then uses the **SPCS session token** (automatically provided by the SPCS runtime) to authenticate with the Snowflake Cortex Agent on the internal network.

## Prerequisites

- Python 3.11+
- Docker (podman can be used an alternative but commands would need to be altered)
- Snowflake account, note that trial accounts do not support SPCS
- Deployed Cortex Agent
- SnowCLI installed with configured connection https://docs.snowflake.com/en/developer-guide/snowflake-cli/connecting/connect


## Configuration Parameters

Before deploying, gather the following information:

| Parameter | Description | How to Find |
|-----------|-------------|-------------|
| `<AGENT_DATABASE>` | Database containing your Cortex Agent | `SHOW DATABASES;` |
| `<AGENT_SCHEMA>` | Schema containing your Cortex Agent | `SHOW SCHEMAS IN DATABASE <db>;` |
| `<AGENT_NAME>` | Name of your Cortex Agent | `SHOW AGENTS IN SCHEMA <db>.<schema>;` |
| `<ACCOUNT_LOCATOR>` | Your Snowflake account locator (for JWT auth) | `SELECT CURRENT_ACCOUNT();` |
| `<USERNAME>` | Your Snowflake username | `SELECT CURRENT_USER();` |

## Deployment

### Step 1: Clone and Setup Environment

```bash
cd spcs_cortex_agent_a2a
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Generate RSA Key Pair (if needed)

```bash
# Generate private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt

# Generate public key
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub

# Get the public key content (for Snowflake)
grep -v "BEGIN\|END" rsa_key.pub | tr -d '\n'
```

### Step 3: Configure Snowflake User

Run this SQL in Snowflake (replace with your public key):

```sql
ALTER USER your_username SET RSA_PUBLIC_KEY='MIIBIjANBgkq...your_public_key...AQAB';

-- Verify the key is set
DESC USER your_username;
-- Look for RSA_PUBLIC_KEY_FP
```

### Step 4: Create Snowflake Resources

Run this SQL in Snowflake (replace <AGENT_DATABASE> and <AGENT_SCHEMA>)

```sql
-- Set your context
USE ROLE ACCOUNTADMIN;
USE DATABASE <AGENT_DATABASE>;
USE SCHEMA <AGENT_SCHEMA>;

-- Create compute pool
CREATE COMPUTE POOL IF NOT EXISTS A2A_AGENT_POOL
    MIN_NODES = 1
    MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_XS
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 1800;

-- Create image repository
CREATE IMAGE REPOSITORY IF NOT EXISTS A2A_IMAGES;

-- Get repository URL (needed for Step 5)
SHOW IMAGE REPOSITORIES LIKE 'A2A_IMAGES';
-- Copy the 'repository_url' value from the output
```

### Step 5: Build and Push Docker Image

```bash
# Set repository URL from Step 4 (paste the repository_url value here once)
export REPO_URL="<repository_url>"

# Set your SnowCLI connection name
export SNOW_CONNECTION="<YOUR_CONNECTION>"

# Build the image
docker build --platform linux/amd64 -t cortex-a2a-agent:latest .

# Login to Snowflake registry
snow spcs image-registry login --connection $SNOW_CONNECTION

# Tag and push (uses REPO_URL variable)
docker tag cortex-a2a-agent:latest $REPO_URL/cortex-a2a-agent:latest
docker push $REPO_URL/cortex-a2a-agent:latest
```

### Step 6: Create the Service

Run this SQL in Snowflake (replace <AGENT_DATABASE>, <AGENT_SCHEMA> and <AGENT_NAME>)

```sql
CREATE SERVICE CORTEX_A2A_AGENT
    IN COMPUTE POOL A2A_AGENT_POOL
    FROM SPECIFICATION $$
spec:
  containers:
    - name: a2a-agent
      image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-a2a-agent:latest
      env:
        AGENT_DATABASE: <AGENT_DATABASE>
        AGENT_SCHEMA: <AGENT_SCHEMA>
        AGENT_NAME: <AGENT_NAME>
        AGENT_DESCRIPTION: "A Snowflake Cortex Agent exposed via the A2A protocol."
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
$$
    MIN_INSTANCES = 1
    MAX_INSTANCES = 1;
```

### Step 7: Get Your Public Endpoint

```sql
-- Check service status (wait for READY)
SELECT SYSTEM$GET_SERVICE_STATUS('CORTEX_A2A_AGENT');

-- Get public endpoint URL
SHOW ENDPOINTS IN SERVICE CORTEX_A2A_AGENT;
-- Copy the 'ingress_url' value
```

## Calling the Service

The SPCS public endpoint requires Snowflake authentication via JWT token.

### Set Environment Variables

```bash
# Ingress url: (paste the ingress_url from Step 7)
export INGRESS_URL="<ingress_url>"

# Account locator: run SELECT CURRENT_ACCOUNT(); in Snowflake
export ACCOUNT_LOCATOR="<account_locator>"

# Username: run SELECT CURRENT_USER(); in Snowflake
export USERNAME="<username>"
```

### Generate JWT Token

The token is short-lived (1 hour) based on the config from file auth.py

```bash
# Generate token
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
        "parts": [{"type": "text", "text": "What data do you have access to?"}]
      }
    }
  }'
```

### Python Example

```python
import os
import requests
from auth import generate_snowflake_jwt

ENDPOINT = f"https://{os.environ['INGRESS_URL']}"
token = generate_snowflake_jwt(
    os.environ["ACCOUNT_LOCATOR"],
    os.environ["USERNAME"],
    "rsa_key.p8"
)
headers = {
    "Content-Type": "application/json",
    "Authorization": f'Snowflake Token="{token}"'
}

response = requests.post(
    f"{ENDPOINT}/",
    headers=headers,
    json={
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "1",
        "params": {
            "message": {
                "messageId": "msg-001",
                "role": "user",
                "parts": [{"type": "text", "text": "How many customers do we have?"}]
            }
        }
    }
)
print(response.json())
```

# 🧪 Testing with test_a2a.py

A lightweight test client is included to verify the A2A server is working correctly.

### Basic Usage

```bash
# In terminal, run the test client
python test_a2a.py
```

### Examples

```bash
# Send a custom query
python test_a2a.py --query "Show me all players from Real Madrid"

# Just check the agent card (discovery endpoint)
python test_a2a.py --card-only
```

## Service Management

```sql
-- View logs
SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_A2A_AGENT', 0, 'a2a-agent', 100);

-- Suspend (stops billing)
ALTER SERVICE CORTEX_A2A_AGENT SUSPEND;

-- Resume
ALTER SERVICE CORTEX_A2A_AGENT RESUME;

-- Delete
DROP SERVICE CORTEX_A2A_AGENT;
DROP COMPUTE POOL A2A_AGENT_POOL;
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Service not starting | Compute pool not ready | Wait for `DESCRIBE COMPUTE POOL` to show ACTIVE/IDLE |
| 401 Unauthorized | Invalid/expired token | Regenerate JWT token (expires after 1 hour) |
| Internal error | Missing SNOWFLAKE_HOST | Don't set SNOWFLAKE_HOST manually - let SPCS provide it |
| Agent not found (404) | Wrong agent path | Verify with `SHOW AGENTS IN SCHEMA <db>.<schema>;` |

---

# External Orchestrator Agent

The `external_agent/` directory contains a second SPCS service that acts as an orchestrator. It runs a local LLM (Qwen2.5-1.5B via llama.cpp) to classify incoming queries and delegates Snowflake data questions to the Cortex A2A agent above via the A2A protocol.

## Architecture

```
                                         SPCS Service (EXTERNAL_A2A_AGENT)
┌─────────────────┐  Public Endpoint  ┌────────────────────────────────────────────────┐
│   A2A Client    │──────────────────▶│  ┌──────────────────┐  ┌───────────────────┐   │
│  (Other Agents) │    (JWT Auth)     │  │  external-agent  │  │    llm-server     │   │
└─────────────────┘                   │  │  (Python, :9000) │  │ (llama.cpp, :8080)│   │
                                      │  │                  │──▶│  Qwen2.5-1.5B    │   │
                                      │  │   Orchestrator   │  │  (Q4_K_M, ~1GB)  │   │
                                      │  └────────┬─────────┘  └───────────────────┘   │
                                      └───────────┼────────────────────────────────────┘
                                                  │ A2A (SPCS internal DNS)
                                      ┌───────────▼────────────────────────────────────┐
                                      │         CORTEX_A2A_AGENT (:8000)               │
                                      │         (from main deployment above)            │
                                      └────────────────────────────────────────────────┘
```

The external agent receives A2A messages, asks the local LLM whether to answer directly or delegate to Snowflake, and routes accordingly. Communication between services uses SPCS internal DNS (no JWT needed).

## Prerequisites

- The **CORTEX_A2A_AGENT** service must be deployed and running (see main deployment above)
- Docker
- SnowCLI

## Deployment

### Step 1: Download and Upload the LLM Model

```bash
cd external_agent
./download_model.sh <SNOW_CONNECTION> <AGENT_DATABASE> <AGENT_SCHEMA>
```

This downloads the Qwen2.5-1.5B-Instruct GGUF model (~1GB) and uploads it to a Snowflake stage (`@LLM_MODELS`).

### Step 2: Build and Push the Docker Image

```bash
export REPO_URL="<repository_url>"    # from SHOW IMAGE REPOSITORIES
export SNOW_CONNECTION="<YOUR_CONNECTION>"

# Build the external agent image
docker build --platform linux/amd64 -t external-a2a-agent:latest .

# Login and push
snow spcs image-registry login --connection $SNOW_CONNECTION
docker tag external-a2a-agent:latest $REPO_URL/external-a2a-agent:latest
docker push $REPO_URL/external-a2a-agent:latest
```

You also need to push the llama.cpp server image to the SPCS registry (SPCS does not allow pulling from external registries):

```bash
docker pull --platform linux/amd64 ghcr.io/ggml-org/llama.cpp:server
docker tag ghcr.io/ggml-org/llama.cpp:server $REPO_URL/llama-cpp-server:latest
docker push $REPO_URL/llama-cpp-server:latest
```

### Step 3: Create the Service

See `external_agent/DEPLOY.sql` for the full SQL. Key points:
- Creates `EXTERNAL_AGENT_POOL` (CPU_X64_S — 2 vCPU, 8GB RAM)
- Creates a two-container service with the llm-server and external-agent
- Update the image paths to use SPCS registry paths (not external registry URLs)

```sql
CREATE COMPUTE POOL IF NOT EXISTS EXTERNAL_AGENT_POOL
    MIN_NODES = 1 MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_S
    AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 1800;
```

### Step 4: Verify and Test

```bash
# Check service status
SELECT SYSTEM$GET_SERVICE_STATUS('EXTERNAL_A2A_AGENT');

# Get the public endpoint
SHOW ENDPOINTS IN SERVICE EXTERNAL_A2A_AGENT;
```

```bash
export INGRESS_URL="<ingress_url>"
export ACCOUNT_LOCATOR="<org_name>-<account_locator>"
export USERNAME="<username>"

# Test
python external_agent/test_external_agent.py --query "What data do you have access to?"
```

## External Agent Service Management

```sql
-- View logs (llm-server)
SELECT SYSTEM$GET_SERVICE_LOGS('EXTERNAL_A2A_AGENT', 0, 'llm-server', 100);

-- View logs (external-agent)
SELECT SYSTEM$GET_SERVICE_LOGS('EXTERNAL_A2A_AGENT', 0, 'external-agent', 100);

-- Suspend / Resume / Delete
ALTER SERVICE EXTERNAL_A2A_AGENT SUSPEND;
ALTER SERVICE EXTERNAL_A2A_AGENT RESUME;
DROP SERVICE EXTERNAL_A2A_AGENT;
DROP COMPUTE POOL EXTERNAL_AGENT_POOL;
```

---

## Resources

- [A2A Protocol](https://github.com/google/a2a)
- [Snowflake Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Snowpark Container Services](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/overview)
- [Snowflake Key-Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)
