"""
Flights Booking A2A Agent executor.
"""
from cortex_executor_base import CortexExecutorBase


class FlightsAgentExecutor(CortexExecutorBase):
    _agent_label = "Flights"
    _fallback_message = "I could not retrieve flight booking information from the Cortex Agent."
