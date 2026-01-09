#!/usr/bin/env python3
"""
Test client for the Snowflake Cortex A2A Agent.

This script demonstrates how to interact with the A2A server using the A2A SDK client.
Make sure the server is running before executing this script.

Usage:
    python test_a2a.py [--query "Your question here"]
    
Examples:
    python test_a2a.py
    python test_a2a.py --query "Who are the top scorers?"
    python test_a2a.py --url http://localhost:8001 --query "Hello"
"""

import asyncio
import argparse
import json
import uuid
import httpx


BASE_URL = "http://localhost:8000"
AGENT_CARD_PATH = "/.well-known/agent.json"


async def fetch_agent_card(base_url: str) -> dict:
    """Fetch the agent card from the server."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}{AGENT_CARD_PATH}")
        response.raise_for_status()
        return response.json()


async def send_message(base_url: str, query: str) -> dict:
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
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()


async def send_message_stream(base_url: str, query: str):
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
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{base_url}/",
            json=request_payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"}
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
        description="Test the Snowflake Cortex A2A Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_a2a.py
  python test_a2a.py --query "What data do you have?"
  python test_a2a.py --url http://localhost:8001
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
        default=BASE_URL,
        help="The base URL of the A2A server (default: http://localhost:8000)"
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
    
    print("\n🔷 Snowflake Cortex A2A Agent Test Client")
    print(f"   Server: {args.url}")
    print()
    
    try:
        # Fetch the agent card
        print("=" * 60)
        print("📋 Fetching Agent Card...")
        print("=" * 60)
        
        agent_card = await fetch_agent_card(args.url)
        
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
            
            async for event in send_message_stream(args.url, args.query):
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
            response = await send_message(args.url, args.query)
            
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
        print(f"\n❌ Connection Error: Could not connect to {args.url}")
        print("\nMake sure the A2A server is running:")
        print("  source venv/bin/activate")
        print("  python main.py")
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error: {e.response.status_code}")
        print(f"   {e.response.text}")
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
