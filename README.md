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
    AUTO_SUSPEND_SECS = 172800
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

## Resources

- [A2A Protocol](https://github.com/google/a2a)
- [Snowflake Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Snowpark Container Services](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/overview)
- [Snowflake Key-Pair Auth](https://docs.snowflake.com/en/user-guide/key-pair-auth)
