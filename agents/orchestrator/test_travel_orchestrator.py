#!/usr/bin/env python3
"""
Test client for the Travel Orchestrator A2A Agent deployed on SPCS.

Uses JWT authentication to connect to the SPCS public endpoint.

Required Environment Variables:
    INGRESS_URL     - The SPCS public endpoint (from SHOW ENDPOINTS IN SERVICE)
    ACCOUNT_LOCATOR - Your Snowflake account locator (SELECT CURRENT_ACCOUNT())
    USERNAME        - Your Snowflake username (SELECT CURRENT_USER())

Usage:
    python test_travel_orchestrator.py
    python test_travel_orchestrator.py --query "What data do you have?"
    python test_travel_orchestrator.py --card-only
"""

import asyncio
import argparse
import json
import os
import sys
import uuid

import httpx

# Add shared directory so we can import auth module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from auth import generate_snowflake_jwt


AGENT_CARD_PATH = "/.well-known/agent-card.json"
DEFAULT_PRIVATE_KEY_PATH = os.path.join(os.path.dirname(__file__), "..", "rsa_key.p8")


def get_auth_headers(account_locator: str, username: str, private_key_path: str) -> dict:
    """Generate authentication headers for SPCS endpoint."""
    token = generate_snowflake_jwt(account_locator, username, private_key_path)
    return {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
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
                "parts": [{"kind": "text", "text": query}],
            }
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base_url}/",
            json=request_payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


async def main():
    parser = argparse.ArgumentParser(
        description="Test the Travel Orchestrator A2A Agent on SPCS",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="What data do you have access to?",
        help="The query to send to the agent",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="The base URL of the A2A server (default: https://$INGRESS_URL)",
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Snowflake account locator (default: $ACCOUNT_LOCATOR)",
    )
    parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="Snowflake username (default: $USERNAME)",
    )
    parser.add_argument(
        "--key",
        type=str,
        default=DEFAULT_PRIVATE_KEY_PATH,
        help="Path to RSA private key",
    )
    parser.add_argument(
        "--card-only",
        action="store_true",
        help="Only fetch and display the agent card",
    )
    args = parser.parse_args()

    ingress_url = args.url or os.environ.get("INGRESS_URL")
    account_locator = args.account or os.environ.get("ACCOUNT_LOCATOR")
    username = args.user or os.environ.get("USERNAME")
    private_key_path = args.key

    missing = []
    if not ingress_url:
        missing.append("INGRESS_URL (or --url)")
    if not account_locator:
        missing.append("ACCOUNT_LOCATOR (or --account)")
    if not username:
        missing.append("USERNAME (or --user)")

    if missing:
        print("\nMissing required configuration:")
        for m in missing:
            print(f"   - {m}")
        print("\nSet environment variables or use command-line arguments.")
        return

    base_url = ingress_url if ingress_url.startswith("https://") else f"https://{ingress_url}"

    if not os.path.exists(private_key_path):
        print(f"\nPrivate key not found: {private_key_path}")
        print("Generate RSA key pair with:")
        print("  openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt")
        return

    print("\n--- Travel Orchestrator A2A Agent Test Client ---")
    print(f"   Endpoint: {base_url}")
    print(f"   Account:  {account_locator}")
    print(f"   User:     {username}")
    print()

    try:
        headers = get_auth_headers(account_locator, username, private_key_path)

        # Fetch agent card
        print("=" * 60)
        print("Fetching Agent Card...")
        print("=" * 60)

        agent_card = await fetch_agent_card(base_url, headers)

        print(f"Name: {agent_card.get('name', 'N/A')}")
        print(f"Description: {agent_card.get('description', 'N/A')}")
        print(f"Version: {agent_card.get('version', 'N/A')}")
        skills = agent_card.get("skills", [])
        if skills:
            print(f"Skills: {[s.get('name') for s in skills]}")

        if args.card_only:
            print("\nAgent card fetched successfully!")
            return

        # Send query
        print("\n" + "=" * 60)
        print(f"Sending Query: {args.query}")
        print("=" * 60)

        response = await send_message(base_url, args.query, headers)

        if "error" in response:
            print(f"\nError from server:")
            print(json.dumps(response["error"], indent=2))
            return

        print("\nRaw JSON Response:")
        print(json.dumps(response, indent=2))

        # Extract agent's text response
        result = response.get("result", {})
        parts = result.get("parts", [])
        if parts:
            print("\n" + "=" * 60)
            print("Agent Response:")
            print("=" * 60)
            for part in parts:
                if part.get("kind") == "text" or part.get("type") == "text":
                    print(part.get("text", ""))

        print("\nTest completed successfully!")

    except httpx.ConnectError:
        print(f"\nConnection Error: Could not connect to {base_url}")
    except httpx.HTTPStatusError as e:
        print(f"\nHTTP Error: {e.response.status_code}")
        print(f"   {e.response.text}")
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
