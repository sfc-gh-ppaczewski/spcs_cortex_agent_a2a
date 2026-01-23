"""
Executor module for Snowflake Cortex A2A Agent.
Implements the A2A AgentExecutor to handle task execution via Snowflake Cortex.

Supports both SPCS (Snowpark Container Services) and local deployment:
- SPCS: Uses session token from /snowflake/session/token
- Local: Uses JWT key-pair authentication
"""
import os
import json
import uuid
import requests
from dotenv import load_dotenv

# A2A SDK Imports
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Message,
    TextPart,
    TaskStatus,
    TaskState
)

# Import our Auth Helper
from auth import is_running_in_spcs, get_auth_token_and_type

load_dotenv()


class SnowflakeCortexExecutor(AgentExecutor):
    """
    Custom A2A executor that interfaces with Snowflake Cortex Agent.
    
    This executor receives tasks from A2A clients, forwards them to the
    configured Snowflake Cortex Agent, and returns the responses.
    
    Supports both SPCS deployment (using session token) and local
    deployment (using JWT key-pair authentication).
    """
    
    def __init__(self):
        """Initialize the executor with Snowflake configuration."""
        self.is_spcs = is_running_in_spcs()
        
        # Agent configuration
        self.db = os.getenv("AGENT_DATABASE")
        self.schema = os.getenv("AGENT_SCHEMA")
        self.agent_name = os.getenv("AGENT_NAME")
        
        # Build API URL based on environment
        if self.is_spcs:
            # In SPCS, use the internal Snowflake host and port
            # SPCS provides SNOWFLAKE_HOST and SNOWFLAKE_PORT for internal network access
            snowflake_host = os.getenv("SNOWFLAKE_HOST")
            snowflake_port = os.getenv("SNOWFLAKE_PORT", "443")
            
            if not snowflake_host:
                raise ValueError(
                    "SNOWFLAKE_HOST must be set in SPCS environment"
                )
            
            # Use internal network - include port if not default
            if snowflake_port == "443":
                self.api_url = f"https://{snowflake_host}/api/v2/databases/{self.db}/schemas/{self.schema}/agents/{self.agent_name}:run"
            else:
                self.api_url = f"https://{snowflake_host}:{snowflake_port}/api/v2/databases/{self.db}/schemas/{self.schema}/agents/{self.agent_name}:run"
            
            print(f"🔷 Snowflake Cortex A2A Agent initialized (SPCS mode)")
            print(f"   Using internal network: {snowflake_host}:{snowflake_port}")
        else:
            # Local development: use account with hyphens for URL
            self.account = os.getenv("SNOWFLAKE_ACCOUNT")
            self.api_url = f"https://{self.account}.snowflakecomputing.com/api/v2/databases/{self.db}/schemas/{self.schema}/agents/{self.agent_name}:run"
            print(f"🔷 Snowflake Cortex A2A Agent initialized (Local mode)")
        
        print(f"   Agent: {self.db}.{self.schema}.{self.agent_name}")
        print(f"   Endpoint: {self.api_url}")

    def _parse_sse_response(self, response) -> str:
        """
        Parse Server-Sent Events (SSE) streaming response from Cortex.
        
        Args:
            response: requests.Response object with streaming content
            
        Returns:
            Concatenated text from all response.text.delta events
        """
        full_text = ""
        
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    # Extract text from response.text.delta events
                    if "text" in data:
                        full_text += data["text"]
                except json.JSONDecodeError:
                    pass
        
        return full_text.strip()

    async def _stream_sse_response(self, response, event_queue: EventQueue) -> str:
        """
        Stream SSE response chunks to the A2A client in real-time.
        
        Args:
            response: requests.Response object with streaming content
            event_queue: Queue to push streaming chunks
            
        Returns:
            Complete text for final message
        """
        full_text = ""
        chunk_buffer = ""
        message_id = str(uuid.uuid4())
        
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if "text" in data:
                        chunk = data["text"]
                        full_text += chunk
                        chunk_buffer += chunk
                        
                        # Send chunks when we have enough content (word boundaries)
                        # This provides smooth streaming without overwhelming the client
                        if len(chunk_buffer) >= 50 or chunk.endswith(('\n', '.', '!', '?')):
                            streaming_msg = Message(
                                messageId=message_id,
                                role="agent",
                                parts=[TextPart(text=chunk_buffer)]
                            )
                            await event_queue.enqueue_event(streaming_msg)
                            chunk_buffer = ""
                            
                except json.JSONDecodeError:
                    pass
        
        # Send any remaining buffer
        if chunk_buffer:
            streaming_msg = Message(
                messageId=message_id,
                role="agent",
                parts=[TextPart(text=chunk_buffer)]
            )
            await event_queue.enqueue_event(streaming_msg)
        
        return full_text.strip()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        The main entry point called by the A2A Protocol when a task is received.
        
        Args:
            context: The A2A request context containing the incoming message
            event_queue: Queue to push status updates and responses
        """
        try:
            # 1. Extract User Input
            incoming_text = "Hello"
            
            if context.message and context.message.parts:
                for part in context.message.parts:
                    # A2A SDK wraps parts in a Part container with a 'root' attribute
                    actual_part = getattr(part, 'root', part)
                    if isinstance(actual_part, TextPart):
                        incoming_text = actual_part.text
                        break
                    elif hasattr(actual_part, 'text'):
                        incoming_text = actual_part.text
                        break
            
            print(f"📥 Received query: {incoming_text}")
            
            # 2. Notify Client: "Processing Started"
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.working)
            )

            # 3. Authenticate (automatically uses SPCS token or JWT based on environment)
            token, token_type = get_auth_token_and_type()

            # 4. Call Snowflake Cortex API
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Snowflake-Authorization-Token-Type": token_type,
                "Accept": "application/json"
            }

            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": incoming_text}]
                    }
                ]
            }

            print(f"🔄 Calling Snowflake Cortex API...")
            response = requests.post(
                self.api_url, 
                json=payload, 
                headers=headers, 
                timeout=120,
                stream=True  # Enable streaming for SSE
            )
            
            if response.status_code != 200:
                error_msg = f"Snowflake API Error {response.status_code}: {response.text}"
                print(f"❌ {error_msg}")
                await event_queue.enqueue_event(
                    TaskStatus(state=TaskState.failed)
                )
                return

            # 5. Parse SSE Response (collect full response for non-streaming A2A)
            content_type = response.headers.get("Content-Type", "")
            
            if "text/event-stream" in content_type:
                # Parse SSE streaming response and collect full text
                print(f"📡 Receiving streaming response from Cortex...")
                final_answer = self._parse_sse_response(response)
            else:
                # Fallback for non-streaming response
                data = response.json()
                final_answer = "I could not retrieve an answer from the Cortex Agent."
                
                if "messages" in data:
                    for msg in reversed(data["messages"]):
                        if msg["role"] in ["assistant", "analyst"]:
                            for content in msg["content"]:
                                if content["type"] == "text":
                                    final_answer = content["text"]
                                    break
                            break
            
            if not final_answer:
                final_answer = "I could not retrieve an answer from the Cortex Agent."
            
            print(f"✅ Got response from Cortex ({len(final_answer)} chars)")
            
            # 6. Send complete response
            response_msg = Message(
                messageId=str(uuid.uuid4()),
                role="agent",
                parts=[TextPart(text=final_answer)]
            )
            await event_queue.enqueue_event(response_msg)
            
            # 7. Mark Task as Complete
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.completed)
            )

        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            print(f"❌ {error_msg}")
            await event_queue.enqueue_event(
                TaskStatus(state=TaskState.failed)
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle task cancellation requests."""
        await event_queue.enqueue_event(
            TaskStatus(state=TaskState.canceled)
        )
