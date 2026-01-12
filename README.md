# 🔷 Snowflake Cortex A2A Agent

An Agent-to-Agent (A2A) protocol wrapper for **any** Snowflake Cortex Agent. This service exposes your Cortex Agent through the Google A2A protocol, enabling other AI agents to interact with it through a standardized interface.

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   A2A Client    │────▶│   A2A Wrapper        │────▶│  Snowflake Cortex   │
│  (Other Agents) │     │   (This Service)     │     │      Agent          │
└─────────────────┘     └──────────────────────┘     └─────────────────────┘
                              │
                              ├── auth.py (JWT Authentication)
                              ├── executor.py (Cortex Integration)
                              └── main.py (A2A Server)
```

**Components:**
- **A2A SDK**: Handles HTTP server, JSON-RPC routing, and protocol compliance
- **Agent Executor**: Custom logic that receives A2A tasks, calls Snowflake, and returns responses
- **Snowflake Cortex**: Your backend Cortex Agent (configurable via environment variables)

## 📋 Prerequisites

- Python 3.11+
- Snowflake account with Cortex Agent access
- RSA key pair for Snowflake authentication
- A deployed Cortex Agent in Snowflake

## 🚀 Quick Start

### 1. Clone and Setup Environment

```bash
cd cortex_agent_a2a
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Generate RSA Key Pair (if needed)

```bash
# Generate private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt

# Generate public key
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub

# Get the public key content (for Snowflake)
grep -v "BEGIN\|END" rsa_key.pub | tr -d '\n'
```

### 3. Configure Snowflake User

Run this SQL in Snowflake (replace with your public key):

```sql
ALTER USER your_username SET RSA_PUBLIC_KEY='MIIBIjANBgkq...your_public_key...AQAB';

-- Verify the key is set
DESC USER your_username;
-- Look for RSA_PUBLIC_KEY_FP
```

### 4. Configure Environment

Create a `.env` file based on `env.template`:

```ini
# Snowflake Connection
SNOWFLAKE_ACCOUNT_LOCATOR=YOUR_ACCOUNT_LOCATOR
SNOWFLAKE_ACCOUNT=YOUR_ORG-YOUR_ACCOUNT
SNOWFLAKE_USER=your_username
PRIVATE_KEY_PATH=rsa_key.p8

# Cortex Agent Details - Point to YOUR agent
AGENT_DATABASE=YOUR_DATABASE
AGENT_SCHEMA=YOUR_SCHEMA
AGENT_NAME=YOUR_CORTEX_AGENT

# Optional: Customize descriptions
AGENT_DESCRIPTION=My custom Cortex Agent description
AGENT_URL=http://localhost:8000
```

**Finding your account identifiers:**
```sql
-- Get account locator (for JWT)
SELECT CURRENT_ACCOUNT();

-- Get full account identifier (for URL - replace underscores with hyphens)
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
```

### 5. Run the Server

```bash
source venv/bin/activate
python main.py
```

The server will start on `http://localhost:8000`

## 🔌 API Endpoints

### Discovery Endpoint

```
GET /.well-known/agent.json
```

Returns the Agent Card describing capabilities:

```json
{
  "name": "Cortex Agent: YOUR_AGENT_NAME",
  "description": "Your agent description...",
  "version": "1.0.0",
  "skills": [
    {
      "id": "query_cortex_agent",
      "name": "Cortex Agent Query",
      "description": "Sends queries to the Snowflake Cortex Agent...",
      "tags": ["snowflake", "cortex", "ai", "analytics"]
    }
  ],
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  }
}
```

### Task Endpoint (JSON-RPC)

```
POST /
Content-Type: application/json
```

**Request:**
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "id": "unique-request-id",
  "params": {
    "message": {
      "messageId": "unique-message-id",
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "Your question here"
        }
      ]
    }
  }
}
```

**Response:**
```json
{
  "jsonrpc": "2.0",
  "id": "unique-request-id",
  "result": {
    "kind": "message",
    "messageId": "response-message-id",
    "role": "agent",
    "parts": [
      {
        "kind": "text",
        "text": "Agent's response..."
      }
    ]
  }
}
```

## 📝 Example Usage

### Using cURL

```bash
# Check agent discovery
curl http://localhost:8000/.well-known/agent.json

# Send a query to the Cortex Agent
curl -X POST http://localhost:8000/ \
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

### Using Python

```python
import requests

# Discovery
response = requests.get("http://localhost:8000/.well-known/agent.json")
print(response.json())

# Query
response = requests.post(
    "http://localhost:8000/",
    json={
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "1",
        "params": {
            "message": {
                "messageId": "msg-001",
                "role": "user",
                "parts": [{"type": "text", "text": "Your question here"}]
            }
        }
    }
)
print(response.json())
```

## 🧪 Testing with test_a2a.py

A lightweight test client is included to verify the A2A server is working correctly.

### Basic Usage

```bash
# Make sure the server is running first
python main.py

# In another terminal, run the test client
python test_a2a.py
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--query "..."` | The question to send to the agent | `"What data do you have access to?"` |
| `--url URL` | Base URL of the A2A server | `http://localhost:8000` |
| `--card-only` | Only fetch the agent card, don't send a query | - |

### Examples

```bash
# Send a custom query
python test_a2a.py --query "Show me all players from Real Madrid"

# Just check the agent card (discovery endpoint)
python test_a2a.py --card-only

# Test against a different server/port
python test_a2a.py --url http://localhost:8001 --query "Hello"
```

### Sample Output

```
🔷 Snowflake Cortex A2A Agent Test Client
   Server: http://localhost:8000

============================================================
📋 Fetching Agent Card...
============================================================
Name: Cortex Agent: YOUR_AGENT_NAME
Description: Your agent description
Version: 1.0.0
Skills: ['Cortex Agent Query']
Streaming: False

============================================================
📨 Sending Query: Show me players from Barcelona
============================================================

📥 Raw JSON Response:
{
  "jsonrpc": "2.0",
  "result": {
    "kind": "message",
    "parts": [{"kind": "text", "text": "..."}]
  }
}

============================================================
🤖 Agent Response
============================================================
Barcelona currently has 3 active players...

✅ Test completed successfully!
```

### Troubleshooting Test Client

**Connection Error:**
```
❌ Connection Error: Could not connect to http://localhost:8000
```
→ Make sure the server is running with `python main.py`

## 🐳 Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t cortex-a2a-agent .

# Run with environment file
docker run -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/rsa_key.p8:/app/rsa_key.p8:ro \
  cortex-a2a-agent
```

### Docker Compose

```yaml
version: '3.8'
services:
  cortex-agent:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./rsa_key.p8:/app/rsa_key.p8:ro
    restart: unless-stopped
```

## 📁 Project Structure

```
cortex_agent_a2a/
├── auth.py              # JWT authentication with SHA256 fingerprint
├── executor.py          # A2A AgentExecutor for Cortex integration
├── main.py              # A2A server entry point
├── test_a2a.py          # Standalone test client
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container deployment
├── .env                 # Environment configuration (create this)
├── .gitignore           # Git ignore rules
├── rsa_key.p8          # RSA private key (generate this)
├── rsa_key.pub         # RSA public key (generate this)
├── env.template         # Environment template
└── README.md           # This file
```

## ⚙️ Configuration Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `SNOWFLAKE_ACCOUNT_LOCATOR` | Account locator for JWT auth | `ABC12345` |
| `SNOWFLAKE_ACCOUNT` | Full account for API URL (use hyphens) | `MYORG-MYACCOUNT` |
| `SNOWFLAKE_USER` | Snowflake username | `my_user` |
| `PRIVATE_KEY_PATH` | Path to RSA private key | `rsa_key.p8` |
| `AGENT_DATABASE` | Database containing the Cortex Agent | `MY_DATABASE` |
| `AGENT_SCHEMA` | Schema containing the Cortex Agent | `MY_SCHEMA` |
| `AGENT_NAME` | Name of the Cortex Agent | `MY_AGENT` |
| `AGENT_DESCRIPTION` | (Optional) Custom agent description | `My AI assistant` |
| `AGENT_URL` | (Optional) Public URL of this service | `http://localhost:8000` |

## 🔐 Security Notes

- **Never commit** `.env`, `rsa_key.p8`, or `rsa_key.pub` to version control
- The `.gitignore` file is configured to exclude sensitive files
- JWT tokens expire after 1 hour and are regenerated per request
- Use HTTPS in production deployments

## 🔧 Troubleshooting

### JWT Token Invalid (390144)

**Cause:** Account identifier format mismatch or key not configured.

**Solution:**
1. Verify public key fingerprint matches in Snowflake: `DESC USER your_username;`
2. Ensure `SNOWFLAKE_ACCOUNT_LOCATOR` uses the short account locator
3. Ensure `SNOWFLAKE_ACCOUNT` uses hyphens, not underscores

### SSL Certificate Error

**Cause:** Account name contains underscores.

**Solution:** Replace ALL underscores with hyphens in `SNOWFLAKE_ACCOUNT`:
```
# Wrong: MYORG-MYACCOUNT_US_WEST_2
# Correct: MYORG-MYACCOUNT-US-WEST-2
```

### Connection Refused

**Cause:** Server not running or wrong port.

**Solution:**
1. Verify server is running: `python main.py`
2. Check logs for startup errors
3. Ensure port 8000 is not in use

### Empty Response

**Cause:** SSE streaming not parsed correctly.

**Solution:** Check that the Cortex Agent is returning valid SSE events. The executor parses `response.text.delta` events.

### Agent Not Found (404)

**Cause:** Incorrect agent path or agent doesn't exist.

**Solution:**
1. Verify the agent exists: `SHOW AGENTS IN SCHEMA {db}.{schema};`
2. Check `AGENT_DATABASE`, `AGENT_SCHEMA`, and `AGENT_NAME` in `.env`
3. Ensure the user has access to the agent

## 🔄 Connecting Multiple Agents

To expose multiple Cortex Agents, run multiple instances with different configurations:

```bash
# Agent 1
AGENT_NAME=SALES_AGENT PORT=8001 python main.py &

# Agent 2  
AGENT_NAME=SUPPORT_AGENT PORT=8002 python main.py &
```

Or use Docker Compose with multiple services.

## 📚 Resources

- [A2A Protocol Specification](https://github.com/google/a2a)
- [Snowflake Cortex Agent Documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Cortex Agents API Reference](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-rest-api)
- [Snowflake Key-Pair Authentication](https://docs.snowflake.com/en/user-guide/key-pair-auth)


## 📄 License

MIT License - See LICENSE file for details.

---

Built with ❄️ Snowflake Cortex and the A2A Protocol
