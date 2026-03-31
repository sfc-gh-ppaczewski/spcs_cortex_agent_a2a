#!/usr/bin/env python3
"""
Test client for the Snowflake Cortex A2A Agent deployed on SPCS.

This script demonstrates how to interact with the A2A server using JWT authentication.
Requires environment variables to be set for SPCS authentication.

Required Environment Variables:
    INGRESS_URL     - The SPCS public endpoint (from SHOW ENDPOINTS IN SERVICE)
    ACCOUNT_LOCATOR - Your Snowflake account locator (SELECT CURRENT_ACCOUNT())
    USERNAME        - Your Snowflake username (SELECT CURRENT_USER())

Usage:
    python test_hotels_agent.py [--query "Your question here"]
    
Examples:
    python test_hotels_agent.py
    python test_hotels_agent.py --query "Who are the top scorers?"
    python test_hotels_agent.py --url https://my-endpoint.snowflakecomputing.app --query "Hello"
"""

import asyncio
import argparse
import base64
import json
import os
import time
import uuid
import httpx
import jwt
from cryptography.hazmat.primitives import serialization, hashes


AGENT_CARD_PATH = "/.well-known/agent-card.json"
DEFAULT_PRIVATE_KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "rsa_key.p8")


def generate_snowflake_jwt(account: str, user: str, private_key_path: str) -> str:
    """Generate a Snowflake JWT for authentication."""
    with open(private_key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)

    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    digest = hashes.Hash(hashes.SHA256())
    digest.update(public_key_der)
    fingerprint = base64.b64encode(digest.finalize()).decode("utf-8")

    qualified_name = f"{account.upper()}.{user.upper()}"

    payload = {
        "iss": f"{qualified_name}.SHA256:{fingerprint}",
        "sub": qualified_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


def get_auth_headers(account_locator: str, username: str, private_key_path: str) -> dict:
    """Generate authentication headers for SPCS endpoint."""
    token = generate_snowflake_jwt(account_locator, username, private_key_path)
    return {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json"
    }


async def fetch_agent_card(base_url: str, headers: dict) -> dict:
    """Fetch the agent card from the server."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}{AGENT_CARD_PATH}", headers=headers)
        response.raise_for_status()
        return response.json()


async def send_message(base_url: str, query: str, headers: dict) -> dict:
    """Send a JSON-RPC message to the agent."""
    
    request_payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": str(uuid.uuid4()),
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": query
                    }
                ]
            }
        }
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url}/",
            json=request_payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()


async def send_message_stream(base_url: str, query: str, headers: dict):
    """Send a streaming JSON-RPC message to the agent and yield chunks."""
    
    request_payload = {
        "jsonrpc": "2.0",
        "method": "message/stream",
        "id": str(uuid.uuid4()),
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": query
                    }
                ]
            }
        }
    }
    
    stream_headers = {**headers, "Accept": "text/event-stream"}
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{base_url}/",
            json=request_payload,
            headers=stream_headers
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        yield data
                    except json.JSONDecodeError:
                        pass


async def main():
    parser = argparse.ArgumentParser(
        description="Test the Snowflake Cortex A2A Agent on SPCS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  INGRESS_URL      - SPCS public endpoint (from SHOW ENDPOINTS IN SERVICE)
  ACCOUNT_LOCATOR  - Snowflake account locator (SELECT CURRENT_ACCOUNT())
  USERNAME         - Snowflake username (SELECT CURRENT_USER())

Examples:
  python test_hotels_agent.py
  python test_hotels_agent.py --query "What data do you have?"
  python test_hotels_agent.py --url https://my-endpoint.snowflakecomputing.app
        """
    )
    parser.add_argument(
        "--query", 
        type=str, 
        default="What data do you have access to?",
        help="The query to send to the agent"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="The base URL of the A2A server (default: https://$INGRESS_URL)"
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Snowflake account locator (default: $ACCOUNT_LOCATOR)"
    )
    parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="Snowflake username (default: $USERNAME)"
    )
    parser.add_argument(
        "--key",
        type=str,
        default=DEFAULT_PRIVATE_KEY_PATH,
        help=f"Path to RSA private key (default: {DEFAULT_PRIVATE_KEY_PATH})"
    )
    parser.add_argument(
        "--card-only",
        action="store_true",
        help="Only fetch and display the agent card, don't send a query"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Show raw JSON events in streaming mode"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Use streaming mode (message/stream instead of message/send)"
    )
    args = parser.parse_args()
    
    # Get configuration from args or environment
    ingress_url = args.url or os.environ.get("INGRESS_URL")
    account_locator = args.account or os.environ.get("ACCOUNT_LOCATOR")
    username = args.user or os.environ.get("USERNAME")
    private_key_path = args.key
    
    # Validate required parameters
    missing = []
    if not ingress_url:
        missing.append("INGRESS_URL (or --url)")
    if not account_locator:
        missing.append("ACCOUNT_LOCATOR (or --account)")
    if not username:
        missing.append("USERNAME (or --user)")
    
    if missing:
        print("\n❌ Missing required configuration:")
        for m in missing:
            print(f"   - {m}")
        print("\nSet environment variables or use command-line arguments.")
        print("See --help for details.")
        return
    
    # Build the base URL
    base_url = ingress_url if ingress_url.startswith("https://") else f"https://{ingress_url}"
    
    # Check private key exists
    if not os.path.exists(private_key_path):
        print(f"\n❌ Private key not found: {private_key_path}")
        print("\nGenerate RSA key pair with:")
        print("  openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt")
        return
    
    print("\n🔷 Snowflake Cortex A2A Agent Test Client (SPCS)")
    print(f"   Endpoint: {base_url}")
    print(f"   Account:  {account_locator}")
    print(f"   User:     {username}")
    print()
    
    try:
        # Generate auth headers
        headers = get_auth_headers(account_locator, username, private_key_path)
        
        # Fetch the agent card
        print("=" * 60)
        print("📋 Fetching Agent Card...")
        print("=" * 60)
        
        agent_card = await fetch_agent_card(base_url, headers)
        
        print(f"Name: {agent_card.get('name', 'N/A')}")
        print(f"Description: {agent_card.get('description', 'N/A')}")
        print(f"Version: {agent_card.get('version', 'N/A')}")
        
        skills = agent_card.get('skills', [])
        if skills:
            print(f"Skills: {[s.get('name') for s in skills]}")
        
        capabilities = agent_card.get('capabilities', {})
        print(f"Streaming: {capabilities.get('streaming', False)}")
        
        if args.card_only:
            print("\n✅ Agent card fetched successfully!")
            return
        
        # Send the query
        print("\n" + "=" * 60)
        mode = "📡 Streaming" if args.stream else "📨 Sending"
        print(f"{mode} Query: {args.query}")
        print("=" * 60)
        
        if args.stream:
            # Streaming mode
            print("\n🤖 Agent Response (streaming):")
            print("-" * 40)
            full_text = ""
            chunk_count = 0
            
            async for event in send_message_stream(base_url, args.query, headers):
                chunk_count += 1
                
                # Handle different event types
                if "error" in event:
                    print(f"\n❌ Error: {json.dumps(event['error'], indent=2)}")
                    return
                
                result = event.get("result", event)
                
                # Check for message events with text parts
                if result.get("kind") == "message":
                    parts = result.get("parts", [])
                    for part in parts:
                        if part.get("kind") == "text":
                            text = part.get("text", "")
                            print(text, end="", flush=True)
                            full_text += text
                
                # Check for status updates
                elif result.get("kind") == "status-update":
                    state = result.get("status", {}).get("state", "")
                    if state == "working":
                        print("⏳ Processing...", flush=True)
                    elif state == "completed":
                        print("\n" + "-" * 40)
                        print(f"✅ Completed ({chunk_count} events received)")
                
                # Show raw events in full mode
                if args.full:
                    print(f"\n[Event {chunk_count}]: {json.dumps(event, indent=2)}")
            
            print(f"\n\n📊 Total response: {len(full_text)} chars")
        
        else:
            # Non-streaming mode
            response = await send_message(base_url, args.query, headers)
            
            # Check for errors
            if "error" in response:
                print(f"\n❌ Error from server:")
                print(json.dumps(response["error"], indent=2))
                return
            
            # Print raw response
            print("\n📥 Raw JSON Response:")
            print(json.dumps(response, indent=2))
            
            # Extract and display the agent's response
            result = response.get("result", {})
            parts = result.get("parts", [])
            
            if parts:
                print("\n" + "=" * 60)
                print("🤖 Agent Response")
                print("=" * 60)
                for part in parts:
                    if part.get("kind") == "text" or part.get("type") == "text":
                        text = part.get("text", "")
                        print(text)
        
        print("\n✅ Test completed successfully!")
            
    except httpx.ConnectError:
        print(f"\n❌ Connection Error: Could not connect to {base_url}")
        print("\nCheck that:")
        print("  1. The SPCS service is running (SELECT SYSTEM$GET_SERVICE_STATUS('...'))")
        print("  2. The INGRESS_URL is correct (SHOW ENDPOINTS IN SERVICE ...)")
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error: {e.response.status_code}")
        print(f"   {e.response.text}")
        if e.response.status_code == 401:
            print("\nAuthentication failed. Check that:")
            print("  1. Your RSA public key is registered with your Snowflake user")
            print("  2. The ACCOUNT_LOCATOR and USERNAME are correct")
            print("  3. The JWT token hasn't expired (tokens last 1 hour)")
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
